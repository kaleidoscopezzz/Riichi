"""Configurable Oka: exact inputs, frozen rules and historical v1 behavior."""
import json
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from rest_framework.exceptions import ValidationError

from .competition_services import finish, generate, ranking, source_versions, write_result
from .models import Tournament, TournamentMachineReservation
from .scoring import rules, score, unpack
from .services import TournamentConflict, mutate_tournament
from .tests_competition import Fixtures


class OkaConfigurationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_user(username="oka_admin", is_staff=True)
        cls.players = [get_user_model().objects.create_user(username=f"oka_player{i}") for i in range(4)]
        cls.ids = [user.player_profile.pk for user in cls.players]

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.admin)
        self.token = self.client.get("/api/v1/auth/csrf/").json()["data"]["csrf_token"]

    def write(self, path="", values=None, method="post"):
        return getattr(self.client, method)("/api/v1/tournaments/" + path, values or {}, content_type="application/json", HTTP_X_CSRFTOKEN=self.token)

    def create(self, **values):
        response = self.write(values={"name": "Oka 独立 QA", "round_count": 1, "participant_ids": self.ids, **values})
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def update(self, row, **values):
        response = self.write(f'{row["id"]}/', values, "patch")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["data"]

    def test_default_derivation_and_zero_decimal_round_trip(self):
        default = self.create()
        self.assertEqual((default["rules_version"], default["rules_source"], default["oka_override"], default["oka"]), (2, "created_v2", None, "20"))
        for supplied, expected in [(0, "0"), ("0.000", "0"), ("+0012.125", "12.125"), ("0." + "1" * 62, "0." + "1" * 62)]:
            with self.subTest(supplied=supplied):
                row = self.create(oka_override=supplied)
                stored = Tournament.objects.get(pk=row["id"])
                detail = self.client.get(f'/api/v1/tournaments/{row["id"]}/').json()["data"]
                self.assertEqual((stored.oka_override, row["oka"], detail["oka_override"]), (expected, expected, expected))
                self.assertEqual((stored.starting_points, stored.return_points), (25000, 30000))
        automatic_zero = self.create(starting_points=30000, return_points=30000)
        self.assertEqual((automatic_zero["oka_override"], automatic_zero["oka"]), (None, "0"))
        self.assertEqual(self.create(starting_points=30000, return_points=25000)["oka"], "-20")

    def test_invalid_oka_is_rejected_without_partial_writes(self):
        row = self.create(oka_override="7.5")
        invalid = [True, False, 0.0, 1.5, -1, "-1", "-0", "", " ", " 0", "0\n", "1e3", "NaN", "Infinity", "1/3", [], {}, "1" * 65]
        for value in invalid:
            with self.subTest(value=value):
                body = {"name": "不得部分保存", "oka_override": value, "participant_ids": []}
                self.assertEqual(self.write(f'{row["id"]}/', body, "patch").status_code, 400)
                self.assertEqual(self.write(values={"round_count": 1, **body}).status_code, 400)
        stored = Tournament.objects.get(pk=row["id"])
        self.assertEqual((stored.name, stored.oka_override, stored.revision, stored.participants.count()), (row["name"], "7.5", 0, 4))
        self.assertEqual(Tournament.objects.count(), 1)

    def test_legacy_draft_only_upgrades_on_explicit_customization_and_can_reset(self):
        row = self.create(rules_version=1)
        row = self.update(row, description="仅改说明")
        self.assertEqual((row["rules_version"], row["rules_source"]), (1, "created_v1"))
        row = self.update(row, oka_override="0", revision=row["revision"])
        self.assertEqual((row["oka"], row["rules_version"], row["rules_source"]), ("0", 2, "draft_configured_v2"))
        row = self.update(row, starting_points=25001, return_points=31000)
        self.assertEqual((row["oka_override"], row["oka"]), ("0", "0"))
        row = self.update(row, oka_override=None)
        self.assertEqual((row["oka_override"], row["oka"], row["rules_version"]), (None, "23.996", 2))
        row = self.update(row, return_points=30000)
        self.assertEqual(row["oka"], "19.996")

    def test_incompatible_or_unknown_rule_versions_are_rejected_atomically(self):
        row = self.create(oka_override="0")
        for values in [{"rules_version": 1}, {"rules_version": 1, "oka_override": "0"}, {"rules_version": 3}, {"rules_version": True}]:
            self.assertEqual(self.write(f'{row["id"]}/', values, "patch").status_code, 400)
        self.assertEqual(self.write(values={"name": "非法版本", "round_count": 1, "rules_version": 1, "oka_override": "0"}).status_code, 400)
        stored = Tournament.objects.get(pk=row["id"])
        self.assertEqual((stored.revision, stored.rules_version, stored.oka_override), (0, 2, "0"))
        # A bad persisted version must fail at start, not silently choose latest.
        row = self.create()
        Tournament.objects.filter(pk=row["id"]).update(rules_version=99)
        self.assertEqual(self.write(f'{row["id"]}/start/').status_code, 400)
        stored = Tournament.objects.get(pk=row["id"])
        self.assertEqual((stored.status, stored.rules_version, stored.revision), ("draft", 99, 0))

    def test_stale_updates_and_started_tournaments_cannot_change_oka(self):
        row = self.create()
        row = self.update(row, oka_override="0", revision=0)
        stale = self.write(f'{row["id"]}/', {"oka_override": "50", "participant_ids": [], "revision": 0}, "patch")
        self.assertEqual(stale.json()["error"]["code"], "stale_tournament")
        self.assertEqual(self.write(f'{row["id"]}/start/').status_code, 200)
        for value in (None, "0", "12.5"):
            frozen = self.write(f'{row["id"]}/', {"oka_override": value}, "patch")
            self.assertEqual((frozen.status_code, frozen.json()["error"]["code"]), (409, "tournament_frozen"))
        stored = Tournament.objects.get(pk=row["id"])
        self.assertEqual((stored.oka, stored.participants.count()), ("0", 4))
        legacy = self.create(rules_version=1)
        started = self.write(f'{legacy["id"]}/start/').json()["data"]
        self.assertEqual((started["rules_version"], started["oka"]), (1, "20"))
        self.assertEqual(self.write(f'{legacy["id"]}/', {"oka_override": "0"}, "patch").status_code, 409)

    def test_oka_write_keeps_admin_and_csrf_guards(self):
        row = self.create()
        url = f'/api/v1/tournaments/{row["id"]}/'
        self.assertEqual(self.client.patch(url, {"oka_override": "0"}, content_type="application/json").status_code, 403)
        for user in (None, self.players[0]):
            client = Client(enforce_csrf_checks=True)
            if user:
                client.force_login(user)
            token = client.get("/api/v1/auth/csrf/").json()["data"]["csrf_token"]
            self.assertEqual(client.patch(url, {"oka_override": "0"}, content_type="application/json", HTTP_X_CSRFTOKEN=token).status_code, 403)
        self.assertIsNone(Tournament.objects.get(pk=row["id"]).oka_override)

    def test_database_oka_constraint_rejects_invalid_state(self):
        row = self.create()
        for values in [{"oka_override": ""}, {"oka_override": "-1"}, {"oka_override": "NaN"}, {"oka_override": "1e3"}, {"oka_override": "0\n"}, {"oka_override": "\n0"}, {"oka_override": "0", "rules_version": 1}]:
            with self.subTest(values=values), self.assertRaises(IntegrityError), transaction.atomic():
                Tournament.objects.filter(pk=row["id"]).update(**values)

    def test_migration_rehearsal_rejects_non_qa_before_opening_a_connection(self):
        from verification.oka_migration_check import rehearse_oka_migration

        for vendor, name in [("sqlite", str(Path(__file__).resolve().parents[1] / "db.sqlite3")), ("postgresql", "riichi"), ("postgresql", "test_riichi"), ("mysql", "riichi_qa_oka")]:
            connection = SimpleNamespace(vendor=vendor, settings_dict={"NAME": name})
            with self.subTest(vendor=vendor, name=name), self.assertRaisesRegex(RuntimeError, "only isolated QA"):
                rehearse_oka_migration(connection)


class OkaScoringTests(Fixtures, TestCase):
    def setUp(self):
        self.setup_data()

    def test_v1_and_v2_automatic_scores_are_identical(self):
        for start, end in [(25000, 30000), (25001, 30000), (30000, 30000), (30000, 25000)]:
            old = Tournament(starting_points=start, return_points=end, rules_version=1, rules_source="created_v1")
            new = Tournament(starting_points=start, return_points=end)
            points = dict(enumerate([start + 10000, start + 10000, start - 10000, start - 10000], 1))
            self.assertEqual(score(old, points), score(new, points))
            self.assertNotIn("oka_override", rules(old))
            self.assertEqual(rules(new)["oka"], new.oka)
        old.oka_override = "0"
        with self.assertRaises(ValidationError):
            score(old, points)

    def test_zero_oka_tie_rewards_and_nonzero_totals_are_exact(self):
        tournament = self.tournament(oka_override="0")
        patterns = [
            ([40000, 30000, 20000, 10000], [30, 10, -10, -30]),
            ([35000, 35000, 20000, 10000], [20, 20, -10, -30]),
            ([40000, 25000, 25000, 10000], [30, 0, 0, -30]),
            ([40000, 30000, 15000, 15000], [30, 10, -20, -20]),
            ([30000, 30000, 30000, 10000], [10, 10, 10, -30]),
            ([40000, 20000, 20000, 20000], [30, -10, -10, -10]),
            ([30000, 30000, 20000, 20000], [20, 20, -20, -20]),
            ([25000] * 4, [0] * 4),
        ]
        for points, bonuses in patterns:
            result = score(tournament, dict(enumerate(points, 1)))
            self.assertEqual([unpack(row["bonus"]) for row in result], bonuses)
            self.assertEqual(sum((unpack(row["score"]) for row in result), Fraction()), -20)

    def test_custom_decimal_multi_round_scores_and_snapshots_are_lossless(self):
        oka = "12." + "1234567890" * 6 + "1"  # 64 characters, beyond Decimal's default precision.
        tournament = self.tournament(rounds=3, oka_override=oka, uma=["30", "10", "-10", "-29"])
        target = None
        reward = (30 + Fraction(oka)) / 3
        for number in range(1, 4):
            round_ = self.first(tournament) if number == 1 else generate(tournament.pk, self.admin, number)
            self.assertEqual(round_.generation_snapshot["rules"]["oka"], oka)
            table = round_.tables.get()
            participants = list(table.seats.values_list("participant_id", flat=True))
            target = target or participants[0]
            last = next(pk for pk in participants if pk != target)
            result = write_result(table.pk, self.admin, 0, points=[{"participant_id": pk, "raw_points": 10000 if pk == last else 30000} for pk in participants], confirm=True)
            self.assertEqual((result["rules"]["oka_override"], result["rules"]["rules_version"]), (oka, 2))
            total = sum((unpack(row["score"]) for row in result["scores"]), Fraction())
            self.assertEqual(total, Fraction(oka) - 19)
            self.assertEqual(json.loads(json.dumps(result["scores"])), result["scores"])
        standing = next(row for row in ranking(tournament)[0] if row["participant_id"] == target)
        self.assertEqual(unpack(standing["total"]), reward * 3)
        self.assertEqual([unpack(row["score"]) for row in standing["rounds"]], [reward] * 3)

    def test_zero_oka_complete_all_roster_sizes_and_freeze_final_snapshot(self):
        for size, rounds in [(4, 1), (8, 3), (12, 2), (16, 6)]:
            tournament = self.tournament(size, rounds, oka_override="0")
            for number in range(1, rounds + 1):
                round_ = self.first(tournament) if number == 1 else generate(tournament.pk, self.admin, number)
                for table in round_.tables.all():
                    self.confirm(table)
            self.resolve(tournament)
            final = finish(tournament.pk, self.admin, source_versions(tournament))
            self.assertEqual((final["rules"]["oka"], final["rules"]["oka_override"]), ("0", "0"))
            self.assertEqual(sum((unpack(row["total"]) for row in final["standings"]), Fraction()), -20 * size // 4 * rounds)
            self.assertFalse(TournamentMachineReservation.objects.filter(table__tournament=tournament, status="active").exists())
            with self.assertRaises(TournamentConflict):
                mutate_tournament(tournament.pk, values={"oka_override": "20"})
            tournament.refresh_from_db()
            self.assertEqual(tournament.final_snapshot, final)
