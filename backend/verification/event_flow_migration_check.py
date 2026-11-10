"""Populated 0009 -> 0010 rehearsal, restricted to explicit isolated QA databases."""
from pathlib import Path
from types import SimpleNamespace

from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from .schema_manifest import build_manifest

BEFORE_EVENT_FLOW = [('tournaments', '0009_pairing_strategies'), ('machines', '0003_remove_mahjongmachine_machine_active_capacity_slot'), ('sessions', '0001_initial')]


def rehearse_event_flow_migration(connection, *, before_upgrade=None):
    name = str(connection.settings_dict['NAME'])
    root = (Path(__file__).resolve().parents[1] / '.verification').resolve()
    isolated = connection.vendor == 'sqlite' and (name == ':memory:' or Path(name).resolve().is_relative_to(root)) or connection.vendor == 'postgresql' and name == 'riichi_qa_event_flow'
    if not isolated:
        raise RuntimeError('Event flow rehearsal accepts only isolated QA databases')
    executor = MigrationExecutor(connection)
    if executor.migration_plan(BEFORE_EVENT_FLOW) or ('tournaments', '0010_event_flow') in executor.loader.applied_migrations:
        raise RuntimeError('Event flow rehearsal requires pre-0010 QA state')
    apps = executor.loader.project_state(BEFORE_EVENT_FLOW).apps
    model = lambda label: apps.get_model(*label.split('.')).objects.using(connection.alias)
    now = timezone.now()
    admin = model('accounts.User').create(username='event_flow_migration_qa_admin', is_staff=True, password='!')
    profiles = [model('players.PlayerProfile').create(user=model('accounts.User').create(username=f'flow_migration_player{i}', password='!'), nickname=f'隔离迁移选手{i}') for i in range(4)]
    machine = model('machines.MahjongMachine').create(machine_no='903', name='隔离迁移旧桌')
    from tournaments.pairing import BONUS_POLICY, SWISS_REPEATS, LEGACY
    from tournaments.scoring import rules, score
    for status, strategy in [('started', SWISS_REPEATS), ('completed', LEGACY)]:
        t = model('tournaments.Tournament').create(name=f'旧赛事 {status}', round_count=2 if status == 'started' else 1,
            created_by=admin, oka_override='0', pairing_strategy=strategy, table_bonus_policy=BONUS_POLICY if strategy != LEGACY else 'none',
            uma=['30.12345678901234567890123456789', '10', '-10', '-30'])
        entries = [model('tournaments.TournamentParticipant').create(tournament=t, player=p, display_name_snapshot=p.nickname) for p in profiles]
        fields = {key: getattr(t, key) for key in ['starting_points', 'return_points', 'uma', 'score_tie_policy', 'champion_tiebreak_policy',
            'rules_version', 'rules_source', 'oka_override', 'pairing_strategy', 'table_bonus_policy', 'ranked_table_bonuses']}
        frozen_rule = SimpleNamespace(**fields, oka='0')
        snapshot = rules(frozen_rule)
        round_ = model('tournaments.TournamentRound').create(tournament=t, round_number=1, generated_by=admin, generation_snapshot={'rules': snapshot})
        fixed = model('tournaments.TournamentTable').create(tournament=t, ordinal=1)
        table = model('tournaments.RoundTable').create(round=round_, table_number=1, tournament_table=fixed,
            base_bonus='0', bonus_source='not_applicable_v1' if strategy != LEGACY else 'legacy_zero', machine_snapshot={'machine_id': machine.pk, 'machine_no': '903'})
        for p, wind in zip(entries, ['east', 'south', 'west', 'north']): model('tournaments.RoundSeat').create(round=round_, table=table, participant=p, seat_wind=wind)
        points = {str(p.pk): 25000 for p in entries}
        scores = score(frozen_rule, points)
        result = model('tournaments.TableResult').create(table=table, status='confirmed', version=2, points=points, scores=scores,
            rule_snapshot=snapshot, edited_by=admin, confirmed_by=admin, confirmed_at=now)
        before_points = {str(p.pk): raw for p, raw in zip(entries, [40000, 30000, 20000, 10000])}
        common = {'table_id': table.pk, 'status': 'confirmed', 'rules': snapshot, 'edited_by': admin.pk, 'edited_at': now.isoformat(),
                  'confirmed_by': admin.pk, 'confirmed_at': now.isoformat()}
        model('tournaments.TableResultCorrection').create(result=result, from_version=1, to_version=2,
            before_snapshot={**common, 'version': 1, 'points': before_points, 'scores': score(frozen_rule, before_points)},
            after_snapshot={**common, 'version': 2, 'points': points, 'scores': scores}, corrected_by=admin, reason='旧阶段QA更正')
        released = status == 'completed'
        audit = {'status': 'released' if released else 'active', 'released_by': admin if released else None,
                 'released_at': now if released else None, 'release_reason': '原始完赛释放说明' if released else ''}
        allocation = model('tournaments.MachineAllocation').create(table=table, machine=machine, machine_no_snapshot='903', allocated_by=admin, **audit)
        model('tournaments.TournamentMachineReservation').create(table=fixed, machine=machine, legacy_allocation=allocation,
            machine_no_snapshot='903', created_by=admin, reason='旧关联建立说明', **audit)
        order = [p.pk for p in entries][::-1]
        lottery = model('tournaments.LotteryRecord').create(tournament=t, source_versions=[{'table_id': table.pk, 'version': 2}],
            members=order, order=order, method='旧公开纸签', description='隔离迁移回归资料', drawn_at=now, created_by=admin,
            confirmed_by=admin if released else None, confirmed_at=now if released else None)
        values = {'status': status, 'started_at': now, 'resource_state': 'fixed', 'first_round_order': [p.pk for p in entries], 'order_source': 'persisted_shuffle_v1'}
        if released:
            by_id = {row['participant_id']: row for row in scores}
            values.update(completed_at=now, completed_by=admin, champion_id=order[0], final_snapshot={'rules': snapshot,
                'champion_id': order[0], 'source_versions': lottery.source_versions, 'lottery_ids': [lottery.pk],
                'standings': [{'participant_id': pk, 'display_name': p.display_name_snapshot, 'rank': index + 1, 'total': by_id[pk]['score'],
                    'first_count': 1, 'second_count': 0, 'confirmed_rounds': 1,
                    'rounds': [{**by_id[pk], 'round_number': 1, 'table_id': table.pk}]} for index, pk in enumerate(order)
                    for p in entries if p.pk == pk]})
        model('tournaments.Tournament').filter(pk=t.pk).update(**values)
    baseline = build_manifest(connection)
    if baseline['result'] != 'PASS': raise AssertionError('Original QA fixture invalid')
    if before_upgrade: before_upgrade(baseline)
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    executor.migrate(targets)
    projection = build_manifest(connection, baseline)
    if projection['result'] != 'PASS': raise AssertionError('0010 changed original columns or identities')
    apps = executor.loader.project_state(targets).apps
    if apps.get_model('tournaments', 'EliminationRecord').objects.using(connection.alias).exists(): raise AssertionError('0010 invented elimination history')
    if apps.get_model('tournaments', 'TournamentParticipant').objects.using(connection.alias).exclude(eliminated_after_round=None).exists(): raise AssertionError('0010 eliminated existing players')
    if apps.get_model('tournaments', 'LotteryRecord').objects.using(connection.alias).exclude(purpose='final', elimination_round=None, participant_statuses=[]).exists(): raise AssertionError('0010 changed historical lottery purpose')
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, 'tournaments_tournamentmachinereservation')
    if 'unique_reserved_machine' in constraints or 'unique_reserved_table' not in constraints: raise AssertionError('Reservation constraints do not match shared association policy')
    current = build_manifest(connection)
    executor = MigrationExecutor(connection); executor.migrate(targets)
    if build_manifest(connection, current)['result'] != 'PASS': raise AssertionError('Migration rerun changed original data')
    return {'result': 'PASS', 'vendor': connection.vendor, 'original_columns_unchanged': True, 'legacy_results_corrections_and_snapshots_unchanged': True,
            'existing_swiss_strategy_unchanged': True, 'elimination_initially_empty': True, 'historical_lotteries_final': True,
            'shared_reservation_constraint': True, 'per_table_unique_preserved': True, 'idempotent_rerun': True, 'additions': projection['additions']}
