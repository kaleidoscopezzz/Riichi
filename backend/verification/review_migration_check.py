"""Shared populated 0004 -> 0005 -> 0006 rehearsal for isolated QA databases.

Call only after the PostgreSQL entry point's empty-QA guard, or from a private
SQLite test connection. Historical migration files are never rewritten.
"""
from django.db import IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from .schema_manifest import build_manifest


BEFORE_REVIEW = [("tournaments", "0004_legacy_compatibility"), ("machines", "0003_remove_mahjongmachine_machine_active_capacity_slot")]
LOTTERY = [("tournaments", "0005_lottery_void"), ("machines", "0003_remove_mahjongmachine_machine_active_capacity_slot")]


def require_empty_qa_postgres(connection):
    if connection.vendor != "postgresql" or connection.settings_dict["NAME"] != "riichi_qa_legacy":
        raise RuntimeError("Refusing to use a non-QA PostgreSQL database")
    if connection.introspection.table_names():
        raise RuntimeError("Use an empty QA database; existing databases are never reset")


def require_unchanged(connection, reference):
    result = build_manifest(connection, reference)
    if result["result"] != "PASS":
        raise AssertionError("Original schema projection or foreign key integrity changed: " + "; ".join(result["differences"]))
    return result


def rehearse_review_migrations(connection, *, tournament_id, admin_id, machine_id, members):
    alias = connection.alias
    executor = MigrationExecutor(connection)
    if executor.migration_plan(BEFORE_REVIEW):
        raise RuntimeError("Review rehearsal requires the exact 0004 historical state")
    applied = executor.loader.applied_migrations
    if ("tournaments", "0005_lottery_void") in applied or ("tournaments", "0006_reservation_release_reason") in applied:
        raise RuntimeError("Review rehearsal refuses an already upgraded database")
    apps = executor.loader.project_state(BEFORE_REVIEW).apps
    now = timezone.now()
    Lottery = apps.get_model("tournaments", "LotteryRecord").objects.using(alias)
    draw = {"tournament_id": tournament_id, "members": members, "order": members[::-1], "source_versions": [], "method": "历史签条", "description": "0005前真实结构的隔离迁移样例", "drawn_at": now, "created_by_id": admin_id}
    pending = Lottery.create(**draw)
    confirmed = Lottery.create(**draw, confirmed_by_id=admin_id, confirmed_at=now)
    fixed = apps.get_model("tournaments", "TournamentTable").objects.using(alias).create(tournament_id=tournament_id, ordinal=1)
    Reservation = apps.get_model("tournaments", "TournamentMachineReservation").objects.using(alias)
    released = Reservation.create(table_id=fixed.pk, machine_id=machine_id, machine_no_snapshot="004", created_by_id=admin_id, status="released", released_at=now, released_by_id=admin_id, reason="旧版正式完赛自动释放")
    active = Reservation.create(table_id=fixed.pk, machine_id=machine_id, machine_no_snapshot="004", created_by_id=admin_id, reason="旧版建立预留原因")
    baseline = build_manifest(connection)
    if baseline["result"] != "PASS":
        raise AssertionError("Invalid historical QA fixture")

    executor = MigrationExecutor(connection)
    executor.migrate(LOTTERY)
    apps = executor.loader.project_state(LOTTERY).apps
    Lottery = apps.get_model("tournaments", "LotteryRecord").objects.using(alias)
    if list(Lottery.filter(pk__in=[pending.pk, confirmed.pk]).order_by("id").values_list("voided_at", "voided_by_id", "void_reason")) != [(None, None, ""), (None, None, "")]:
        raise AssertionError("0005 historical audit defaults differ")
    violations = [(pending.pk, {"voided_at": now}), (pending.pk, {"voided_at": now, "voided_by_id": admin_id}), (confirmed.pk, {"voided_at": now, "voided_by_id": admin_id, "void_reason": "已确认不得作废"})]
    for target, values in violations:
        try:
            with transaction.atomic(using=alias):
                Lottery.filter(pk=target).update(**values)
        except IntegrityError:
            continue
        raise AssertionError("0005 lottery_void_state did not reject invalid audit state")
    require_unchanged(connection, baseline)

    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    executor.migrate(targets)
    apps = executor.loader.project_state(targets).apps
    Reservation = apps.get_model("tournaments", "TournamentMachineReservation").objects.using(alias)
    expected = [(released.pk, "released", "旧版正式完赛自动释放", "旧版正式完赛自动释放"), (active.pk, "active", "旧版建立预留原因", "")]
    if list(Reservation.filter(pk__in=[released.pk, active.pk]).order_by("id").values_list("id", "status", "reason", "release_reason")) != expected:
        raise AssertionError("0006 release reason copy changed the original reason or active row")
    projected = require_unchanged(connection, baseline)
    current = build_manifest(connection)
    executor = MigrationExecutor(connection)
    if executor.migration_plan(executor.loader.graph.leaf_nodes()):
        raise AssertionError("Pending migrations remain after rehearsal")
    executor.migrate(executor.loader.graph.leaf_nodes())
    require_unchanged(connection, current)
    return {"result": "PASS", "database_vendor": connection.vendor, "old_lottery_rows": 2, "pre_0006_reservations": 2, "invalid_void_states_rejected": len(violations), "original_columns_unchanged": True, "released_only_copy": True, "migration_rerun_noop": True, "additions": projected["additions"]}
