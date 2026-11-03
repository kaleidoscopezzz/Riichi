from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client, TestCase, TransactionTestCase

from .models import MahjongMachine
from .services import MachineConflict, create_machine


class MachineApiTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username="machine_admin", is_staff=True)
        self.user = get_user_model().objects.create_user(username="machine_user")
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.admin)
        self.token = self.client.get("/api/v1/auth/csrf/").json()["data"]["csrf_token"]

    def write(self, path="", data=None, method="post", token=None):
        return getattr(self.client, method)("/api/v1/machines/" + path, data or {}, content_type="application/json", HTTP_X_CSRFTOKEN=token or self.token)

    def create(self, number="101", **values):
        return self.write(data={"machine_no": number, "name": "测试物理设备", **values})

    def test_create_normalization_and_details(self):
        response = self.create("7", location="测试区", description="独立备注")
        self.assertEqual(response.status_code, 201)
        machine = response.json()["data"]
        self.assertEqual(machine["machine_no"], "007")
        self.assertEqual(machine["status"], "available")
        self.assertNotIn("capacity_slot", machine)
        self.assertEqual(self.client.get(f'/api/v1/machines/{machine["id"]}/').json()["data"], machine)

    def test_permission_matrix(self):
        machine = self.create().json()["data"]
        for who in [None, self.user]:
            client = Client(enforce_csrf_checks=True)
            if who:
                client.force_login(who)
            token = client.get("/api/v1/auth/csrf/").json()["data"]["csrf_token"]
            for method, path, data in [("get", "", None), ("get", f'{machine["id"]}/', None), ("post", "", {"machine_no": "102", "name": "拒绝"}), ("patch", f'{machine["id"]}/', {"name": "拒绝"}), ("post", f'{machine["id"]}/retire/', {})]:
                with self.subTest(user=bool(who), method=method, path=path):
                    response = getattr(client, method)("/api/v1/machines/" + path, data, content_type="application/json", HTTP_X_CSRFTOKEN=token)
                    self.assertEqual(response.status_code, 403)

    def test_duplicate_normalized_number_and_edit_conflict(self):
        first = self.create("1").json()["data"]
        self.assertEqual(self.create("001").json()["error"]["code"], "duplicate_machine_no")
        second = self.create("200").json()["data"]
        response = self.write(f'{second["id"]}/', {"machine_no": "1"}, "patch")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(MahjongMachine.objects.get(pk=second["id"]).machine_no, "200")
        self.assertNotEqual(first["id"], second["id"])

    def test_field_validation(self):
        for value in ["", "abc", "12a", "1234", "１", "-1"]:
            self.assertEqual(self.create(value).status_code, 400)
        for values in [{"name": " "}, {"name": "x" * 101}, {"location": "x" * 201}, {"description": "x" * 2001}, {"status": "unknown"}, {"status": "retired"}, {"capacity_slot": 1}, {"id": 7}]:
            self.assertEqual(self.create(**values).status_code, 400)
        self.assertEqual(self.write(data=[]).status_code, 400)

    def test_four_active_and_capacity_released_by_retirement(self):
        items = []
        for number, state in [("101", "available"), ("202", "maintenance"), ("303", "disabled"), ("999", "available")]:
            response = self.create(number, status=state)
            self.assertEqual(response.status_code, 201)
            items.append(response.json()["data"])
        fifth = self.create("555")
        self.assertEqual(fifth.status_code, 409)
        self.assertEqual(fifth.json()["error"]["code"], "machine_capacity_full")
        original = items[1]
        self.assertEqual(self.write(f'{original["id"]}/retire/').status_code, 200)
        replacement = self.create("202")
        self.assertEqual(replacement.status_code, 201)
        self.assertNotEqual(replacement.json()["data"]["id"], original["id"])
        historical = MahjongMachine.objects.get(pk=original["id"])
        self.assertEqual(historical.status, "retired")
        self.assertIsNone(historical.capacity_slot)
        self.assertEqual(historical.name, original["name"])
        self.assertEqual(MahjongMachine.objects.exclude(status="retired").count(), 4)

    def test_state_transitions_and_terminal_state(self):
        pk = self.create().json()["data"]["id"]
        for state in ["maintenance", "available", "disabled", "available", "disabled", "maintenance"]:
            response = self.write(f"{pk}/", {"status": state, "location": "新位置"}, "patch")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["data"]["status"], state)
        self.assertEqual(self.write(f"{pk}/", {"status": "retired"}, "patch").status_code, 400)
        self.assertEqual(self.write(f"{pk}/retire/", {"name": "不能编辑"}).status_code, 400)
        self.assertEqual(self.write(f"{pk}/retire/").status_code, 200)
        before = MahjongMachine.objects.get(pk=pk)
        self.assertEqual(self.write(f"{pk}/retire/").json()["error"]["code"], "already_retired")
        for values in [{"status": "available"}, {"name": "不能改"}]:
            self.assertEqual(self.write(f"{pk}/", values, "patch").json()["error"]["code"], "retired_readonly")
        before.refresh_from_db()
        self.assertEqual(before.status, "retired")
        self.assertEqual(before.location, "新位置")

    def test_search_filter_order_pagination_and_global_summary(self):
        self.create("500", name="青竹", status="maintenance")
        self.create("010", name="白玉")
        for i in range(21):
            MahjongMachine.objects.create(machine_no="999", name=f"历史{i}", status="retired")
        response = self.client.get("/api/v1/machines/").json()["data"]
        self.assertEqual(response["count"], 23)
        self.assertEqual(len(response["results"]), 20)
        self.assertEqual([row["machine_no"] for row in response["results"][:2]], ["010", "500"])
        self.assertIsNotNone(response["next"])
        self.assertEqual(len(self.client.get("/api/v1/machines/?page=2").json()["data"]["results"]), 3)
        for query in ["search=青竹", "search=500", "status=maintenance"]:
            filtered = self.client.get("/api/v1/machines/?" + query).json()["data"]
            self.assertEqual(filtered["count"], 1)
            self.assertEqual(filtered["summary"]["active"], 2)
            self.assertEqual(filtered["summary"]["retired"], 21)
        self.assertEqual(self.client.get("/api/v1/machines/?status=invalid").status_code, 400)
        self.assertEqual(self.client.get("/api/v1/machines/?page=500").status_code, 404)

    def test_csrf_required_for_all_writes(self):
        pk = self.create().json()["data"]["id"]
        for method, path, body in [("post", "", {"machine_no": "002", "name": "拒绝"}), ("patch", f"{pk}/", {"status": "disabled"}), ("post", f"{pk}/retire/", {})]:
            for headers in [{}, {"HTTP_X_CSRFTOKEN": "invalid"}]:
                response = getattr(self.client, method)("/api/v1/machines/" + path, body, content_type="application/json", **headers)
                self.assertEqual(response.status_code, 403)

    def test_no_delete_or_put(self):
        pk = self.create().json()["data"]["id"]
        for method in ["delete", "put"]:
            self.assertEqual(self.write(f"{pk}/", {"name": "拒绝"}, method).status_code, 405)
        self.assertTrue(MahjongMachine.objects.filter(pk=pk).exists())


class MachineConstraintTests(TestCase):
    def test_invalid_rows_rejected_without_serializer(self):
        for values in [{"capacity_slot": None}, {"capacity_slot": 0}, {"capacity_slot": 5}, {"status": "unknown"}, {"machine_no": "1"}, {"machine_no": "ABC"}, {"machine_no": "100\n"}, {"name": "  "}, {"status": "retired", "capacity_slot": 1}]:
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                MahjongMachine.objects.create(**({"name": "约束验证", "machine_no": "100", "capacity_slot": 1} | values))

    def test_unique_slots_and_active_numbers(self):
        create_machine({"machine_no": "100", "name": "设备"})
        for values in [{"machine_no": "101", "capacity_slot": 1}, {"machine_no": "100", "capacity_slot": 2}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                MahjongMachine.objects.create(name="重复", **values)
        for _ in range(2):
            MahjongMachine.objects.create(machine_no="100", name="历史设备", status="retired")

    def test_direct_fifth_active_cannot_bypass_capacity(self):
        for number in range(4):
            create_machine({"machine_no": f"{number:03}", "name": "设备"})
        for slot in [None, 1, 2, 3, 4, 5]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                MahjongMachine.objects.create(machine_no="999", name="第五台", capacity_slot=slot)


class ConcurrentMachineTests(TransactionTestCase):
    def test_concurrent_creation_never_exceeds_capacity(self):
        barrier = Barrier(8)

        def worker(number):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                create_machine({"machine_no": f"{number + 100:03}", "name": "并发设备"})
                return "created"
            except MachineConflict as exc:
                return exc.default_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(worker, range(8)))
        self.assertTrue(set(results) <= {"created", "machine_busy", "machine_capacity_full"})
        count = MahjongMachine.objects.exclude(status="retired").count()
        self.assertGreater(count, 0)
        self.assertLessEqual(count, 4)
        self.assertEqual(count, results.count("created"))
