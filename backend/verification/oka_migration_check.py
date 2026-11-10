"""Populated 0006 -> 0007 rehearsal, only on an explicitly prepared QA connection."""
from pathlib import Path
from types import SimpleNamespace

from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from .schema_manifest import build_manifest


BEFORE_OKA = [("tournaments", "0006_reservation_release_reason"), ("machines", "0003_remove_mahjongmachine_machine_active_capacity_slot"), ("sessions", "0001_initial")]


def rehearse_oka_migration(connection, *, before_upgrade=None):
    name = str(connection.settings_dict["NAME"])
    qa_root = (Path(__file__).resolve().parents[1] / ".verification").resolve()
    isolated = (
        connection.vendor == "sqlite" and (name == ":memory:" or Path(name).resolve().is_relative_to(qa_root))
        or connection.vendor == "postgresql" and name == "riichi_qa_oka"
    )
    if not isolated:
        raise RuntimeError("Oka rehearsal accepts only isolated QA databases")
    executor = MigrationExecutor(connection)
    if executor.migration_plan(BEFORE_OKA) or ("tournaments", "0007_configurable_oka") in executor.loader.applied_migrations:
        raise RuntimeError("Oka rehearsal requires the exact pre-0007 QA migration state")
    apps = executor.loader.project_state(BEFORE_OKA).apps
    alias = connection.alias
    model = lambda label: apps.get_model(*label.split(".")).objects.using(alias)
    now = timezone.now()
    admin = model("accounts.User").create(username="oka_migration_admin", is_staff=True)
    profiles = [model("players.PlayerProfile").create(user=model("accounts.User").create(username=f"oka_migration_player{i}"), nickname=f"隔离迁移选手{i}") for i in range(4)]
    cases = [("draft", 25000, 30000, "20"), ("started", 25001, 30000, "19.996"), ("completed", 30000, 30000, "0"), ("started", 30000, 25000, "-20")]
    expected = {}
    from tournaments.scoring import rules, score

    for index, (status, start, end, oka) in enumerate(cases):
        tournament = model("tournaments.Tournament").create(name=f"隔离旧规则 {index}", round_count=1 if status == "completed" else 2, starting_points=start, return_points=end, created_by=admin, rules_source="legacy_default_backfill:0004")
        participants = [model("tournaments.TournamentParticipant").create(tournament=tournament, player=profile, display_name_snapshot=profile.nickname if status != "draft" else "") for profile in profiles]
        expected[tournament.pk] = oka
        if status == "draft":
            continue
        old_rule = SimpleNamespace(**{key: getattr(tournament, key) for key in ["starting_points", "return_points", "uma", "score_tie_policy", "champion_tiebreak_policy", "rules_version", "rules_source"]}, oka_override=None)
        rule_snapshot = rules(old_rule)
        round_ = model("tournaments.TournamentRound").create(tournament=tournament, round_number=1, generated_by=admin, generation_snapshot={"rules": rule_snapshot})
        table = model("tournaments.RoundTable").create(round=round_, table_number=1)
        for participant, wind in zip(participants, ["east", "south", "west", "north"]):
            model("tournaments.RoundSeat").create(round=round_, table=table, participant=participant, seat_wind=wind)
        points = {str(participant.pk): start + delta for participant, delta in zip(participants, [15000, 5000, -5000, -15000])}
        scores = score(old_rule, points)
        model("tournaments.TableResult").create(table=table, status="confirmed", points=points, scores=scores, rule_snapshot=rule_snapshot, edited_by=admin, confirmed_by=admin, confirmed_at=now)
        values = {"status": status, "started_at": now}
        if status == "completed":
            values.update(completed_at=now, completed_by=admin, champion=participants[0], final_snapshot={"rules": rule_snapshot, "champion_id": participants[0].pk, "standings": [{"participant_id": row["participant_id"], "rank": row["rank"], "total": row["score"]} for row in scores]})
        model("tournaments.Tournament").filter(pk=tournament.pk).update(**values)

    baseline = build_manifest(connection)
    if baseline["result"] != "PASS":
        raise AssertionError("Invalid populated Oka migration fixture")
    if before_upgrade is not None:
        before_upgrade(baseline)
    executor = MigrationExecutor(connection)
    targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] != 'tournaments'] + [('tournaments', '0007_configurable_oka')]
    executor.migrate(targets)
    projection = build_manifest(connection, baseline)
    if projection["result"] != "PASS":
        raise AssertionError("0007 changed historical columns, rows, keys or snapshots")

    from tournaments.rules import derive_oka
    Tournament = executor.loader.project_state(targets).apps.get_model('tournaments', 'Tournament')
    for tournament in Tournament.objects.using(alias).filter(pk__in=expected):
        tournament.oka = derive_oka(tournament.starting_points, tournament.return_points)
        if (tournament.oka_override, tournament.rules_version, tournament.rules_source, tournament.oka) != (None, 1, "legacy_default_backfill:0004", expected[tournament.pk]):
            raise AssertionError("0007 changed a historical tournament's scoring configuration")
        for round_ in tournament.rounds.all():
            for table in round_.tables.all():
                if score(tournament, table.result.points) != table.result.scores:
                    raise AssertionError("Legacy score changed after 0007")
    new = executor.loader.project_state(targets).apps.get_model("tournaments", "Tournament")()
    if (new.rules_version, new.rules_source, new.oka_override) != (2, "created_v2", None):
        raise AssertionError("New tournament defaults differ")
    current = build_manifest(connection)
    executor = MigrationExecutor(connection)
    if executor.migration_plan(targets):
        raise AssertionError("Oka migrations still pending")
    executor.migrate(targets)
    if build_manifest(connection, current)["result"] != "PASS":
        raise AssertionError("Migration rerun changed data")
    return {"result": "PASS", "vendor": connection.vendor, "historical_tournaments": len(expected), "confirmed_results": 3, "completed_snapshots": 1, "original_columns_unchanged": True, "legacy_oka_values": list(expected.values()), "new_rule_version": 2, "migration_rerun_noop": True, "additions": projection["additions"]}
