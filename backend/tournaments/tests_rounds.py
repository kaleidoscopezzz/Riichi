from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from rest_framework.exceptions import ValidationError

from machines.models import MahjongMachine
from machines.services import create_machine, change_machine, MachineConflict
from .models import TournamentRound, RoundTable, RoundSeat, MachineAllocation
from .services import create_tournament, mutate_tournament, TournamentConflict
from .round_services import change_allocation, validate_round_structure
from .legacy_test_fixture import generate_first_round

User = get_user_model()


class RoundFixtures:
    def prepare(self):
        self.admin = User.objects.create_user(username="round_admin", is_staff=True)
        self.users = [User.objects.create_user(username=f"round_player{i}") for i in range(16)]
        self.ids = [u.player_profile.pk for u in self.users]
        self.machines = [create_machine({"name": f"设备{number}", "machine_no": number}) for number in ["303", "010", "999", "102"]]

    def tournament(self, size=4, started=True):
        row = create_tournament(self.admin, {"name": "轮次验证", "round_count": 6, "participant_ids": self.ids[:size]})
        return mutate_tournament(row.pk, start=True) if started else row

    def release_all(self, round):
        for table in round.tables.all():
            change_allocation(table.pk, self.admin, reason="验证释放")


class RoundTests(RoundFixtures, TestCase):
    def setUp(self):
        self.prepare()
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.admin)
        self.token = self.client.get("/api/v1/auth/csrf/").json()["data"]["csrf_token"]

    def write(self, path, body=None, method="post"):
        return getattr(self.client, method)("/api/v1/" + path, body if body is not None else {}, content_type="application/json", HTTP_X_CSRFTOKEN=self.token)

    def test_four_sizes_complete_seats_and_ordered_machine_assignment(self):
        for size in [4, 8, 12, 16]:
            row = self.tournament(size)
            result = self.write(f"tournaments/{row.pk}/rounds/", {"round_number": 1, "machine_ids": [m.pk for m in sorted(self.machines, key=lambda m: m.machine_no)[:size//4]]})
            self.assertEqual(result.status_code, 201, result.content)
            tables = result.json()["data"]["tables"]
            self.assertEqual(len(tables), size // 4)
            self.assertEqual([t["machine_snapshot"]["machine_no"] for t in tables], ["010", "102", "303", "999"][:size // 4])
            for table in tables:
                self.assertEqual([s["seat_wind"] for s in table["seats"]], ["east", "south", "west", "north"])
                self.assertEqual(len(table["seats"]), 4)
                self.assertTrue(all(s["display_name"] for s in table["seats"]))
            seats = [s["participant_id"] for t in tables for s in t["seats"]]
            self.assertEqual(len(set(seats)), size)
            self.assertEqual(set(seats), set(row.participants.values_list("id", flat=True)))
            from .models import TournamentMachineReservation
            from .competition_services import release_reservation
            for reservation in TournamentMachineReservation.objects.filter(table__tournament=row, status="active"):
                release_reservation(reservation, self.admin, "测试夹具清理")

    def test_injectable_random_source_persisted_and_not_overwritten(self):
        class ReverseRandom:
            calls = 0
            def shuffle(self, values):
                self.calls += 1
                values.reverse()
        rng = ReverseRandom()
        row = self.tournament(8)
        before = list(row.participants.values_list("pk", flat=True))
        result = generate_first_round(row.pk, self.admin, rng=rng)
        self.assertEqual(rng.calls, 1)
        self.assertEqual(list(result.seats.order_by("pk").values_list("participant_id", flat=True)), before[::-1])
        first = self.client.get(f"/api/v1/tournaments/{row.pk}/rounds/1/").json()
        self.assertEqual(self.write(f"tournaments/{row.pk}/rounds/", {"round_number": 1}).json()["error"]["code"], "round_already_generated")
        self.assertEqual(self.client.get(f"/api/v1/tournaments/{row.pk}/rounds/1/").json(), first)

    def test_draft_later_invalid_and_client_seating_rejected(self):
        draft = self.tournament(started=False)
        self.assertEqual(self.write(f"tournaments/{draft.pk}/rounds/", {"round_number": 1}).json()["error"]["code"], "tournament_not_started")
        row = self.tournament()
        for number in [2, 3, 4, 5, 6]:
            response = self.write(f"tournaments/{row.pk}/rounds/", {"round_number": number})
            self.assertEqual((response.status_code, response.json()["error"]["code"]), (409, "round_not_next"))
        for body in [{"round_number": 0}, {"round_number": 7}, {"round_number": True}, {"round_number": 1.0}, {"round_number": 1, "seats": []}, {"round_number": 1, "machine_id": 1}]:
            self.assertEqual(self.write(f"tournaments/{row.pk}/rounds/", body).status_code, 400)
        self.assertFalse(TournamentRound.objects.exists())

    def test_excludes_unavailable_and_other_tournaments_without_pool_exclusivity(self):
        first = generate_first_round(self.tournament(8).pk, self.admin)
        second = generate_first_round(self.tournament(8).pk, self.admin)
        self.assertEqual(set(first.tables.values_list("allocations__machine__machine_no", flat=True)), {"010", "102"})
        self.assertEqual(set(second.tables.values_list("allocations__machine__machine_no", flat=True)), {"303", "999"})
        with self.assertRaises(TournamentConflict) as error:
            generate_first_round(self.tournament().pk, self.admin)
        self.assertEqual(error.exception.default_code, "insufficient_machines")
        self.release_all(first)
        self.release_all(second)
        for machine, status in zip(self.machines[:3], ["maintenance", "disabled", "retired"], strict=True):
            change_machine(machine.pk, {"status": status} if status != "retired" else None, retire=status == "retired")
        row = self.tournament(8)
        with self.assertRaises(TournamentConflict):
            generate_first_round(row.pk, self.admin)
        self.assertFalse(row.rounds.exists())
        generated = generate_first_round(self.tournament().pk, self.admin)
        self.assertEqual(generated.tables.get().allocations.get().machine_id, self.machines[3].pk)

    def test_generation_failure_rolls_back_all_entities(self):
        row = self.tournament(8)
        create = MachineAllocation.objects.create
        calls = 0
        def fail_second(**values):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise IntegrityError("injected second allocation failure")
            return create(**values)
        with patch("tournaments.round_services.MachineAllocation.objects.create", side_effect=fail_second), self.assertRaises(TournamentConflict):
            generate_first_round(row.pk, self.admin)
        self.assertEqual([m.objects.count() for m in [TournamentRound, RoundTable, RoundSeat, MachineAllocation]], [0, 0, 0, 0])
        row.refresh_from_db()
        self.assertEqual(row.status, "started")

    def test_reassign_history_same_machine_and_failed_target_keep_original(self):
        round = generate_first_round(self.tournament(8).pk, self.admin)
        first, second = list(round.tables.all())
        original = first.allocations.get()
        other = second.allocations.get()
        for target, code in [(original.machine_id, "machine_unchanged"), (other.machine_id, "machine_occupied")]:
            with self.assertRaises(TournamentConflict) as error:
                change_allocation(first.pk, self.admin, machine_id=target)
            self.assertEqual(error.exception.default_code, code)
        self.assertEqual(self.write(f"round-tables/{first.pk}/machine/reassign/", {"machine_id": 999999}).status_code, 404)
        target = self.machines[0]
        # A PostgreSQL phantom inserted after the pool snapshot must not be used
        # without a row lock, even when the ID now exists.
        with patch("tournaments.round_services.lock_machine_pool", return_value=[m for m in self.machines if m.pk != target.pk]), self.assertRaises(TournamentConflict):
            change_allocation(first.pk, self.admin, machine_id=target.pk)
        self.assertEqual(first.allocations.filter(status="active").get().pk, original.pk)
        change_machine(target.pk, {"status": "maintenance"})
        with self.assertRaises(TournamentConflict):
            change_allocation(first.pk, self.admin, machine_id=target.pk)
        self.assertEqual(first.allocations.filter(status="active").get().pk, original.pk)
        change_machine(target.pk, {"status": "available"})
        response = self.write(f"round-tables/{first.pk}/machine/reassign/", {"machine_id": target.pk})
        self.assertEqual(response.status_code, 200)
        history = response.json()["data"]["allocation_history"]
        self.assertEqual([h["status"] for h in history], ["released", "active"])
        self.assertEqual(history[0]["released_by"], self.admin.pk)
        self.assertIsNotNone(history[0]["released_at"])
        self.assertEqual(history[1]["machine_id"], target.pk)
        with patch("tournaments.round_services.MachineAllocation.objects.create", side_effect=IntegrityError("injected replacement failure")), self.assertRaises(TournamentConflict):
            change_allocation(first.pk, self.admin, machine_id=self.machines[2].pk)
        self.assertEqual(first.allocations.filter(status="active").get().machine_id, target.pk)
        self.assertEqual(first.allocations.count(), 2)

    def test_release_terminal_audit_and_number_snapshot(self):
        round = generate_first_round(self.tournament().pk, self.admin)
        table = round.tables.get()
        allocation = table.allocations.get()
        change_machine(allocation.machine_id, {"machine_no": "011", "name": "可以编辑"})
        response = self.write(f"round-tables/{table.pk}/machine/release/", {"reason": "实体对局结束，非成绩确认"})
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertIsNone(data["active_allocation"])
        self.assertEqual(data["allocation_history"][0]["machine_no_snapshot"], "010")
        self.assertEqual(data["allocation_history"][0]["machine_no"], "011")
        self.assertEqual(len(data["seats"]), 4)
        self.assertEqual(self.write(f"round-tables/{table.pk}/machine/release/").json()["error"]["code"], "allocation_released")
        self.assertEqual(self.write(f"round-tables/{table.pk}/machine/reassign/", {"machine_id": self.machines[0].pk}).status_code, 409)
        history = self.client.get(f"/api/v1/round-tables/{table.pk}/machine/history/").json()["data"]["results"]
        self.assertEqual(len(history), 1)
        change_machine(allocation.machine_id, retire=True)
        self.assertEqual(MachineAllocation.objects.get(pk=allocation.pk).machine_id, allocation.machine_id)
        self.assertTrue(self.client.get(f"/api/v1/machine-resources/").json()["data"]["results"])
        round.tournament.refresh_from_db()
        self.assertEqual(round.tournament.status, "started")

    def test_busy_machine_state_protection_and_free_after_release(self):
        round = generate_first_round(self.tournament().pk, self.admin)
        allocation = round.tables.get().allocations.get()
        for status in ["maintenance", "disabled"]:
            with self.assertRaises(MachineConflict) as error:
                change_machine(allocation.machine_id, {"status": status})
            self.assertEqual(error.exception.default_code, "machine_in_use")
        with self.assertRaises(MachineConflict):
            change_machine(allocation.machine_id, retire=True)
        change_machine(allocation.machine_id, {"location": "仍可编辑位置"})
        self.release_all(round)
        change_machine(allocation.machine_id, {"status": "maintenance"})
        change_machine(allocation.machine_id, retire=True)

    def test_database_constraints(self):
        round = generate_first_round(self.tournament(8).pk, self.admin)
        first, second = list(round.tables.all())
        allocation = first.allocations.get()
        invalid_allocations = [
            {"table": second, "machine_id": allocation.machine_id},
            {"table": first, "machine": self.machines[2]},
            {"table": first, "machine": self.machines[2], "status": "released"},
            {"table": first, "machine": self.machines[2], "status": "bad"},
        ]
        for values in invalid_allocations:
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                MachineAllocation.objects.create(**values, machine_no_snapshot="999", allocated_by=self.admin)
        for value in [0, 7]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                TournamentRound.objects.create(tournament=round.tournament, round_number=value, generated_by=self.admin)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TournamentRound.objects.create(tournament=round.tournament, round_number=1, generated_by=self.admin)
        for number in [0, 1, 5]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                RoundTable.objects.create(round=round, table_number=number)
        for wind in ["east", "up"]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                RoundSeat.objects.create(round=round, table=first, participant=first.seats.first().participant, seat_wind=wind)
        seat = second.seats.first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoundSeat.objects.create(round=round, table=first, participant=seat.participant, seat_wind="north")

    def test_cross_table_invariants_checked_by_service_not_claimed_as_check(self):
        round = generate_first_round(self.tournament().pk, self.admin)
        other = self.tournament()
        foreign = other.participants.first()
        seat = round.seats.first()
        seat.participant = foreign
        with self.assertRaises(ModelValidationError):
            seat.clean()
        other_round = TournamentRound.objects.create(tournament=other, round_number=1, generated_by=self.admin)
        seat = round.seats.first()
        seat.round = other_round
        with self.assertRaises(ModelValidationError):
            seat.clean()
        # Direct SQL/ORM can bypass cross-table clean; integrity audit catches it.
        RoundSeat.objects.filter(pk=round.seats.first().pk).update(participant=foreign)
        with self.assertRaises(ValidationError):
            validate_round_structure(round)

    def test_database_unique_constraints_are_independently_exercised(self):
        round = generate_first_round(self.tournament().pk, self.admin)
        first = round.tables.get()
        empty = RoundTable.objects.create(round=round, table_number=2)
        original = first.allocations.get()
        # Empty table has no active allocation: only active MACHINE uniqueness fails.
        with self.assertRaises(IntegrityError), transaction.atomic():
            MachineAllocation.objects.create(table=empty, machine_id=original.machine_id, allocated_by=self.admin, machine_no_snapshot="010")
        # Free machine: only active TABLE uniqueness fails.
        with self.assertRaises(IntegrityError), transaction.atomic():
            MachineAllocation.objects.create(table=first, machine=self.machines[0], allocated_by=self.admin, machine_no_snapshot="303")
        # Empty table/wind: only per-round PARTICIPANT uniqueness fails.
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoundSeat.objects.create(round=round, table=empty, participant=first.seats.first().participant, seat_wind="east")
        # Fresh participant ID isolates WIND uniqueness. The separate clean tests
        # cover cross-tournament ownership, which this SQL constraint cannot express.
        fresh = self.tournament().participants.first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoundSeat.objects.create(round=round, table=first, participant=fresh, seat_wind="east")
        from django.utils import timezone
        for values in [{"released_at": timezone.now()}, {"status": "released", "released_at": timezone.now()}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                MachineAllocation.objects.create(table=empty, machine=self.machines[0], allocated_by=self.admin, machine_no_snapshot="303", **values)

    def test_permissions_csrf_strict_fields_and_no_seat_edits_or_deletes(self):
        row = self.tournament()
        round = generate_first_round(row.pk, self.admin)
        table = round.tables.get()
        operations = [("get", f"tournaments/{row.pk}/rounds/", {}), ("get", f"tournaments/{row.pk}/rounds/1/", {}), ("get", f"round-tables/{table.pk}/", {}), ("get", f"round-tables/{table.pk}/machine/history/", {}), ("get", "machine-resources/", {}), ("post", f"tournaments/{row.pk}/rounds/", {"round_number": 1}), ("post", f"round-tables/{table.pk}/machine/reassign/", {"machine_id": self.machines[0].pk}), ("post", f"round-tables/{table.pk}/machine/release/", {})]
        for user in [None, self.users[0]]:
            client = Client(enforce_csrf_checks=True)
            if user:
                client.force_login(user)
            token = client.get("/api/v1/auth/csrf/").json()["data"]["csrf_token"]
            for method, path, body in operations:
                self.assertEqual(getattr(client, method)("/api/v1/" + path, body, content_type="application/json", HTTP_X_CSRFTOKEN=token).status_code, 403)
        for method, path, body in operations[-3:]:
            for headers in [{}, {"HTTP_X_CSRFTOKEN": "invalid"}]:
                self.assertEqual(getattr(self.client, method)("/api/v1/" + path, body, content_type="application/json", **headers).status_code, 403)
        for suffix, body in [("machine/reassign/", {"machine_id": self.machines[0].pk, "seats": []}), ("machine/release/", {"reason": "x", "status": "active"})]:
            self.assertEqual(self.write(f"round-tables/{table.pk}/{suffix}", body).status_code, 400)
        for method in ["patch", "put", "delete"]:
            self.assertEqual(self.write(f"round-tables/{table.pk}/", {}, method).status_code, 405)


class ConcurrentRoundTests(RoundFixtures, TransactionTestCase):
    def setUp(self):
        self.prepare()

    def race(self, functions):
        barrier = Barrier(len(functions))
        def worker(fn):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                fn()
                return "ok"
            except (TournamentConflict, MachineConflict) as exc:
                return exc.default_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            return list(pool.map(worker, functions))

    def audit(self):
        active = list(MachineAllocation.objects.filter(status="active").select_related("machine"))
        self.assertEqual(len({a.machine_id for a in active}), len(active))
        self.assertEqual(len({a.table_id for a in active}), len(active))
        self.assertTrue(all(a.machine.status == "available" for a in active))
        for row in TournamentRound.objects.all():
            validate_round_structure(row)

    def test_same_tournament_concurrent_generation(self):
        row = self.tournament()
        result = self.race([lambda: generate_first_round(row.pk, self.admin)] * 4)
        self.assertEqual(result.count("ok"), 1, result)
        self.assertEqual(row.rounds.count(), 1)
        self.audit()

    def test_different_tournaments_compete_for_same_pool(self):
        a, b = self.tournament(16), self.tournament(16)
        result = self.race([lambda: generate_first_round(a.pk, self.admin), lambda: generate_first_round(b.pk, self.admin)])
        self.assertEqual(result.count("ok"), 1, result)
        self.assertEqual(TournamentRound.objects.count(), 1)
        self.audit()

    def test_generation_vs_state_changes(self):
        row = self.tournament(16)
        result = self.race([lambda: generate_first_round(row.pk, self.admin), lambda: change_machine(self.machines[0].pk, {"status": "disabled"}), lambda: change_machine(self.machines[1].pk, retire=True)])
        self.assertTrue(set(result) <= {"ok", "insufficient_machines", "machine_in_use", "machine_busy", "tournament_busy"}, result)
        self.audit()

    def test_reassign_vs_generation_and_release(self):
        first = generate_first_round(self.tournament().pk, self.admin)
        table = first.tables.get()
        row = self.tournament(12)
        result = self.race([lambda: change_allocation(table.pk, self.admin, machine_id=self.machines[0].pk), lambda: generate_first_round(row.pk, self.admin), lambda: change_allocation(table.pk, self.admin, reason="并发释放")])
        self.assertTrue(set(result) <= {"ok", "allocation_released", "machine_occupied", "insufficient_machines", "tournament_busy"}, result)
        self.audit()
