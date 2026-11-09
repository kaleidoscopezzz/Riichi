"""Populated 0007 -> 0008 upgrade; accepts only explicitly isolated QA databases."""
from pathlib import Path
from types import SimpleNamespace

from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from .schema_manifest import build_manifest


BEFORE_CORRECTIONS = [('tournaments', '0007_configurable_oka'), ('machines', '0003_remove_mahjongmachine_machine_active_capacity_slot'), ('sessions', '0001_initial')]


def rehearse_result_correction_migration(connection, *, before_upgrade=None):
    name = str(connection.settings_dict['NAME'])
    root = (Path(__file__).resolve().parents[1] / '.verification').resolve()
    isolated = connection.vendor == 'sqlite' and (name == ':memory:' or Path(name).resolve().is_relative_to(root)) or connection.vendor == 'postgresql' and name == 'riichi_qa_result_corrections'
    if not isolated:
        raise RuntimeError('Result correction rehearsal accepts only isolated QA databases')
    executor = MigrationExecutor(connection)
    if executor.migration_plan(BEFORE_CORRECTIONS) or ('tournaments', '0008_result_corrections') in executor.loader.applied_migrations:
        raise RuntimeError('Result correction rehearsal requires the exact pre-0008 state')
    apps = executor.loader.project_state(BEFORE_CORRECTIONS).apps
    alias = connection.alias
    model = lambda label: apps.get_model(*label.split('.')).objects.using(alias)
    now = timezone.now()
    admin = model('accounts.User').create(username='correction_migration_qa_admin', is_staff=True)
    profiles = [model('players.PlayerProfile').create(user=model('accounts.User').create(username=f'correction_migration_qa_player{i}'), nickname=f'隔离迁移选手{i}') for i in range(4)]
    machine = model('machines.MahjongMachine').create(machine_no='901', name='隔离迁移物理桌')
    from tournaments.rules import derive_oka
    from tournaments.scoring import rules, score

    for index, status in enumerate(['started', 'completed']):
        tournament = model('tournaments.Tournament').create(name=f'隔离迁移 {status}', round_count=1, created_by=admin, rules_version=index + 1, rules_source=f'created_v{index + 1}', oka_override=None if index == 0 else '0')
        entries = [model('tournaments.TournamentParticipant').create(tournament=tournament, player=profile, display_name_snapshot=profile.nickname) for profile in profiles]
        fixed = model('tournaments.TournamentTable').create(tournament=tournament, ordinal=1)
        rule = SimpleNamespace(**{key: getattr(tournament, key) for key in ['starting_points', 'return_points', 'uma', 'score_tie_policy', 'champion_tiebreak_policy', 'rules_version', 'rules_source', 'oka_override']}, oka=derive_oka(tournament.starting_points, tournament.return_points) if tournament.oka_override is None else tournament.oka_override)
        snapshot = rules(rule)
        round_ = model('tournaments.TournamentRound').create(tournament=tournament, round_number=1, generated_by=admin, generation_snapshot={'rules': snapshot, 'source_versions': []})
        table = model('tournaments.RoundTable').create(round=round_, table_number=1, tournament_table=fixed, machine_snapshot={'machine_id': machine.pk, 'machine_no': machine.machine_no})
        for participant, wind in zip(entries, ['east', 'south', 'west', 'north']):
            model('tournaments.RoundSeat').create(round=round_, table=table, participant=participant, seat_wind=wind)
        points = {str(entry.pk): 25000 for entry in entries}
        scores = score(rule, points)
        result = model('tournaments.TableResult').create(table=table, status='confirmed', version=2, points=points, scores=scores, rule_snapshot=snapshot, edited_by=admin, confirmed_by=admin, confirmed_at=now)
        released = status == 'completed'
        allocation = model('tournaments.MachineAllocation').create(table=table, machine=machine, machine_no_snapshot='901', allocated_by=admin, status='released' if released else 'active', released_by=admin if released else None, released_at=now if released else None, release_reason='隔离QA历史释放' if released else '')
        model('tournaments.TournamentMachineReservation').create(table=fixed, machine=machine, legacy_allocation=allocation, machine_no_snapshot='901', created_by=admin, status='released' if released else 'active', released_by=admin if released else None, released_at=now if released else None, reason='隔离QA建立预留', release_reason='隔离QA历史释放' if released else '')
        order = [entry.pk for entry in entries][::-1]
        lottery = model('tournaments.LotteryRecord').create(tournament=tournament, source_versions=[{'table_id': table.pk, 'version': result.version}], members=order, order=order, method='隔离QA签条', description='迁移回归样例，不是真实赛事', drawn_at=now, created_by=admin, rules_version=tournament.rules_version, confirmed_by=admin if released else None, confirmed_at=now if released else None)
        state = {'status': status, 'started_at': now, 'resource_state': 'fixed', 'first_round_order': [entry.pk for entry in entries], 'order_source': 'initial_random_v1'}
        if released:
            by_id = {row['participant_id']: row for row in scores}
            state.update(completed_at=now, completed_by=admin, champion_id=order[0], final_snapshot={'rules': snapshot, 'source_versions': lottery.source_versions, 'lottery_ids': [lottery.pk], 'champion_id': order[0], 'standings': [{'participant_id': pk, 'rank': rank, 'total': by_id[pk]['score']} for rank, pk in enumerate(order, 1)]})
        model('tournaments.Tournament').filter(pk=tournament.pk).update(**state)

    baseline = build_manifest(connection)
    if baseline['result'] != 'PASS':
        raise AssertionError('Historical QA fixture integrity failed')
    if before_upgrade is not None:
        before_upgrade(baseline)
    executor = MigrationExecutor(connection)
    # This historical rehearsal verifies 0008, even after later migrations exist.
    targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] != 'tournaments'] + [('tournaments', '0008_result_corrections')]
    executor.migrate(targets)
    result = build_manifest(connection, baseline)
    if result['result'] != 'PASS':
        raise AssertionError('0008 changed original rows, columns, identities or snapshots')
    apps = executor.loader.project_state(targets).apps
    if apps.get_model('tournaments', 'TableResultCorrection').objects.using(alias).exists():
        raise AssertionError('0008 must not invent historical corrections')
    current = build_manifest(connection)
    executor = MigrationExecutor(connection)
    if executor.migration_plan(targets):
        raise AssertionError('Migrations still pending after 0008')
    executor.migrate(targets)
    if build_manifest(connection, current)['result'] != 'PASS':
        raise AssertionError('Idempotent migration rerun changed data')
    return {'result': 'PASS', 'vendor': connection.vendor, 'old_tournaments': 2, 'old_confirmed_results': 2, 'old_lotteries': 2, 'old_legacy_allocations': 2, 'old_reservations': 2, 'original_columns_unchanged': True, 'audit_initially_empty': True, 'idempotent_rerun': True, 'additions': result['additions']}
