from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from rest_framework.exceptions import ValidationError

from .models import Tournament, TournamentParticipant
from .rules import canonical_uma, derive_oka
from .services import TournamentConflict, create_tournament, mutate_tournament

User = get_user_model()


class TournamentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username="tournament_admin", is_staff=True)
        cls.users = [User.objects.create_user(username=f"entrant{i}") for i in range(16)]
        cls.ids = [user.player_profile.pk for user in cls.users]

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.admin)
        self.token = self.client.get("/api/v1/auth/csrf/").json()["data"]["csrf_token"]

    def write(self, path="", body=None, method="post", **headers):
        return getattr(self.client, method)("/api/v1/tournaments/" + path, body if body is not None else {}, content_type="application/json", HTTP_X_CSRFTOKEN=self.token, **headers)

    def create(self, **values):
        response = self.write(body={"name": "冬季个人赛", "round_count": 3, **values})
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def test_defaults_independent_config_and_exact_oka(self):
        first = self.create()
        self.assertEqual((first["starting_points"], first["return_points"], first["uma"], first["oka"]), (25000, 30000, ["30", "10", "-10", "-30"], "20"))
        second = self.create(starting_points=25001, uma=["30.1", "9.9", "-10", "-30"])
        self.assertEqual(second["oka"], "19.996")
        self.assertEqual(Tournament.objects.get(pk=first["id"]).uma, first["uma"])
        self.assertEqual(derive_oka(30000, 25000), "-20")
        self.assertEqual(canonical_uma([1, "0.000000001", 2, -3])[1], "0.000000001")

    def test_invalid_config_unknown_and_internal_fields(self):
        bad = [{"round_count": v} for v in [0, 7, True, 1.5, "3"]]
        bad += [{key: value} for key in ["starting_points", "return_points"] for value in [0, -1, True, 1.5, "25000", 2147483648]]
        bad += [{"uma": v} for v in [[1, 2], [1, 2, 3, 4, 5], [True, 1, 2, 3], ["NaN", 1, 2, 3], ["1e3", 1, 2, 3], [0.1, 1, 2, 3]]]
        bad += [{key: value} for key, value in [("status", "started"), ("created_by", self.admin.pk), ("started_at", None), ("oka", 20), ("revision", 4), ("name", " ")]]
        for values in bad:
            with self.subTest(values=values):
                self.assertEqual(self.write(body={"name": "测试", "round_count": 1, **values}).status_code, 400)
        self.assertEqual(Tournament.objects.count(), 0)

    def test_draft_edit_and_roster_replacement(self):
        row = self.create(participant_ids=self.ids[:3])
        self.assertIsNone(row["expected_table_count"])
        response = self.write(f'{row["id"]}/', {"name": "新名称", "round_count": 6}, "patch")
        self.assertEqual(response.json()["data"]["name"], "新名称")
        ids = self.ids[:3] + [self.admin.player_profile.pk]
        response = self.write(f'{row["id"]}/participants/', {"participant_ids": ids}, "put")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["participant_count"], 4)
        self.assertEqual(response.json()["data"]["expected_table_count"], 1)
        self.assertTrue(all(not p["display_name_snapshot"] for p in response.json()["data"]["participants"]))
        self.assertEqual(self.write(f'{row["id"]}/start/').status_code, 200)

    def test_invalid_rosters_are_atomic(self):
        row = self.create(participant_ids=self.ids[:4])
        self.users[5].is_active = False
        self.users[5].save()
        bad = [[self.ids[0]] * 4, [999999], [self.ids[5]], self.ids + [999999], [True], [1.0], ["1"]]
        for ids in bad:
            with self.subTest(ids=ids):
                self.assertEqual(self.write(f'{row["id"]}/participants/', {"participant_ids": ids}, "put").status_code, 400)
                self.assertEqual(TournamentParticipant.objects.filter(tournament_id=row["id"]).count(), 4)
        count = Tournament.objects.count()
        self.assertEqual(self.write(body={"name": "回滚", "round_count": 1, "participant_ids": [999999]}).status_code, 400)
        self.assertEqual(Tournament.objects.count(), count)
        response = self.write(f'{row["id"]}/', {"name": "不得部分保存", "participant_ids": [999999]}, "patch")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Tournament.objects.get(pk=row["id"]).name, row["name"])

    def test_existing_player_query_eligible_filter_preserves_contract(self):
        self.users[0].is_active = False
        self.users[0].save()
        original = self.client.get("/api/v1/players/").json()["data"]
        eligible = self.client.get("/api/v1/players/?eligible=true").json()["data"]
        self.assertEqual(original["count"], 17)
        self.assertEqual(eligible["count"], 16)
        self.assertNotIn(self.ids[0], [player["id"] for player in eligible["results"]])
        self.assertIn(self.admin.player_profile.pk, [player["id"] for player in eligible["results"]])
        self.assertEqual(set(original["results"][0]), set(eligible["results"][0]))
        self.assertEqual(self.client.get("/api/v1/players/?eligible=invalid").status_code, 400)

    def test_all_legal_sizes_start_and_snapshot_freeze(self):
        for size in (4, 8, 12, 16):
            row = self.create(participant_ids=self.ids[:size])
            response = self.write(f'{row["id"]}/start/')
            self.assertEqual(response.status_code, 200, response.content)
            data = response.json()["data"]
            self.assertEqual(data["status"], "started")
            self.assertIsNotNone(data["started_at"])
            self.assertEqual(data["expected_table_count"], size // 4)
            before = data["participants"][0]["display_name"]
            profile = self.users[0].player_profile
            profile.nickname = f"后来改名{size}"
            profile.save()
            self.assertEqual(self.client.get(f'/api/v1/tournaments/{row["id"]}/').json()["data"]["participants"][0]["display_name"], before)
            self.assertEqual(self.write(f'{row["id"]}/', {"name": "拒绝"}, "patch").status_code, 409)
            self.assertEqual(self.write(f'{row["id"]}/participants/', {"participant_ids": []}, "put").status_code, 409)
            self.assertEqual(self.write(f'{row["id"]}/start/').json()["error"]["code"], "already_started")
            self.assertEqual(self.write(f'{row["id"]}/', {}, "delete").status_code, 405)
            self.assertTrue(Tournament.objects.filter(pk=row["id"]).exists())

    def test_invalid_start_count_and_deactivated_player(self):
        for size in (0, 1, 3, 5, 7, 9, 15):
            row = self.create(participant_ids=self.ids[:size])
            self.assertEqual(self.write(f'{row["id"]}/start/').status_code, 400)
            current = Tournament.objects.get(pk=row["id"])
            self.assertEqual(current.status, "draft")
            self.assertIsNone(current.started_at)
            self.assertEqual(current.revision, 0)
        row = self.create(participant_ids=self.ids[:4])
        self.users[0].is_active = False
        self.users[0].save()
        self.assertEqual(self.write(f'{row["id"]}/start/').status_code, 400)
        self.assertFalse(TournamentParticipant.objects.filter(tournament_id=row["id"]).exclude(display_name_snapshot="").exists())

    def test_snapshot_failure_rolls_back_everything(self):
        row = self.create(participant_ids=self.ids[:4])
        # Fail AFTER snapshot bulk_update has written, before state/time save.
        with patch("tournaments.services.Tournament.save", side_effect=IntegrityError("injected write failure")):
            with self.assertRaises(IntegrityError):
                mutate_tournament(row["id"], start=True)
        current = Tournament.objects.get(pk=row["id"])
        self.assertEqual((current.status, current.revision, current.started_at), ("draft", 0, None))
        self.assertFalse(current.participants.exclude(display_name_snapshot="").exists())

    def test_start_revalidates_persisted_uma(self):
        row = self.create(participant_ids=self.ids[:4])
        Tournament.objects.filter(pk=row["id"]).update(uma=["NaN", "1", "2", "3"])
        self.assertEqual(self.write(f'{row["id"]}/start/').status_code, 400)
        self.assertEqual(Tournament.objects.get(pk=row["id"]).status, "draft")

    def test_permissions_all_endpoints_and_csrf(self):
        row = self.create(participant_ids=self.ids[:4])
        operations = [("get", "", {}), ("get", f'{row["id"]}/', {}), ("post", "", {"name": "拒绝", "round_count": 1}), ("patch", f'{row["id"]}/', {"name": "拒绝"}), ("put", f'{row["id"]}/participants/', {"participant_ids": []}), ("post", f'{row["id"]}/start/', {})]
        for user in (None, self.users[0]):
            client = Client(enforce_csrf_checks=True)
            if user:
                client.force_login(user)
            token = client.get("/api/v1/auth/csrf/").json()["data"]["csrf_token"]
            for method, path, body in operations:
                self.assertEqual(getattr(client, method)("/api/v1/tournaments/" + path, body, content_type="application/json", HTTP_X_CSRFTOKEN=token).status_code, 403)
        for method, path, body in operations[2:]:
            for headers in ({}, {"HTTP_X_CSRFTOKEN": "invalid"}):
                self.assertEqual(getattr(self.client, method)("/api/v1/tournaments/" + path, body, content_type="application/json", **headers).status_code, 403)

    def test_list_search_status_pagination_no_delete_or_state_injection(self):
        row = self.create()
        for i in range(21):
            create_tournament(self.admin, {"name": f"其他赛事{i}", "round_count": 1})
        data = self.client.get("/api/v1/tournaments/").json()["data"]
        self.assertEqual((data["count"], len(data["results"])), (22, 20))
        self.assertIsNotNone(data["next"])
        self.assertEqual(self.client.get("/api/v1/tournaments/?search=冬季&status=draft").json()["data"]["count"], 1)
        self.assertEqual(self.client.get("/api/v1/tournaments/?status=cancelled").status_code, 400)
        self.assertEqual(self.client.get("/api/v1/tournaments/?page=2").status_code, 200)
        self.assertEqual(self.write(f'{row["id"]}/', {}, "delete").status_code, 405)
        self.assertEqual(self.write(f'{row["id"]}/', {"status": "started"}, "patch").status_code, 400)
        self.assertEqual(self.write(f'{row["id"]}/start/', {"status": "started"}).status_code, 400)

    def test_database_constraints_and_unique_participants(self):
        row = self.create(participant_ids=self.ids[:4])
        for values in [{"round_count": 0}, {"round_count": 7}, {"starting_points": 0}, {"return_points": 0}, {"status": "cancelled"}, {"status": "started"}, {"name": " "}]:
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                Tournament.objects.filter(pk=row["id"]).update(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TournamentParticipant.objects.create(tournament_id=row["id"], player_id=self.ids[0])


class ConcurrentTournamentTests(TransactionTestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="race_admin", is_staff=True)
        self.ids = [User.objects.create_user(username=f"race{i}").player_profile.pk for i in range(8)]

    def race(self, functions):
        barrier = Barrier(len(functions))
        def worker(fn):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                fn()
                return "ok"
            except TournamentConflict as exc:
                return exc.default_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            return list(pool.map(worker, functions))

    def test_parallel_start_only_one_commits(self):
        row = create_tournament(self.admin, {"name": "并发启动", "round_count": 1, "participant_ids": self.ids[:4]})
        results = self.race([lambda: mutate_tournament(row.pk, start=True)] * 4)
        self.assertEqual(results.count("ok"), 1, results)
        self.assertTrue(set(results) <= {"ok", "already_started", "tournament_busy"})
        row.refresh_from_db()
        self.assertEqual((row.status, row.revision), ("started", 1))
        self.assertEqual(row.participants.exclude(display_name_snapshot="").count(), 4)

    def test_start_vs_roster_and_config_edits_are_serial(self):
        row = create_tournament(self.admin, {"name": "并发编辑", "round_count": 1, "participant_ids": self.ids[:4]})
        results = self.race([lambda: mutate_tournament(row.pk, start=True), lambda: mutate_tournament(row.pk, participant_ids=self.ids[4:]), lambda: mutate_tournament(row.pk, values={"round_count": 6})])
        self.assertTrue(set(results) <= {"ok", "tournament_frozen", "tournament_busy"}, results)
        row.refresh_from_db()
        # If SQLite rejects the starter as busy, finish explicitly then verify.
        if row.status == "draft":
            mutate_tournament(row.pk, start=True)
        row.refresh_from_db()
        entries = list(row.participants.all())
        self.assertIn({e.player_id for e in entries}, [set(self.ids[:4]), set(self.ids[4:])])
        self.assertEqual(len(entries), 4)
        self.assertTrue(all(e.display_name_snapshot for e in entries))
        with self.assertRaises(TournamentConflict):
            mutate_tournament(row.pk, values={"name": "冻结后拒绝"})
