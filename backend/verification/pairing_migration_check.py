"""Populated 0008 -> 0009 rehearsal, restricted to explicit QA databases."""
from pathlib import Path
from types import SimpleNamespace
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from .schema_manifest import build_manifest

BEFORE_PAIRING = [('tournaments', '0008_result_corrections'), ('machines', '0003_remove_mahjongmachine_machine_active_capacity_slot'), ('sessions', '0001_initial')]


def rehearse_pairing_migration(connection, *, before_upgrade=None):
    name = str(connection.settings_dict['NAME'])
    root = (Path(__file__).resolve().parents[1] / '.verification').resolve()
    if not (connection.vendor == 'sqlite' and (name == ':memory:' or Path(name).resolve().is_relative_to(root)) or connection.vendor == 'postgresql' and name == 'riichi_qa_pairing'):
        raise RuntimeError('Pairing rehearsal accepts only isolated QA databases')
    executor = MigrationExecutor(connection)
    if executor.migration_plan(BEFORE_PAIRING) or ('tournaments', '0009_pairing_strategies') in executor.loader.applied_migrations:
        raise RuntimeError('Pairing rehearsal requires pre-0009 QA state')
    apps = executor.loader.project_state(BEFORE_PAIRING).apps
    model = lambda label: apps.get_model(*label.split('.')).objects.using(connection.alias)
    now = timezone.now()
    admin = model('accounts.User').create(username='pairing_migration_qa', is_staff=True)
    profiles = [model('players.PlayerProfile').create(user=model('accounts.User').create(username=f'pair_mig_player{i}'), nickname=f'隔离迁移选手{i}') for i in range(4)]
    machine = model('machines.MahjongMachine').create(machine_no='902', name='隔离迁移旧桌')
    from tournaments.scoring import rules, score
    from tournaments.rules import derive_oka
    from tournaments.models import Tournament
    expected = {}
    for index, state in enumerate(['started', 'completed']):
        t = model('tournaments.Tournament').create(name=f'原规则 {state}', round_count=1, created_by=admin, rules_version=index+1, rules_source=f'created_v{index+1}', oka_override=None if index == 0 else '0')
        entries = [model('tournaments.TournamentParticipant').create(tournament=t, player=p, display_name_snapshot=p.nickname) for p in profiles]
        t_fields = {key: getattr(t, key) for key in ['starting_points', 'return_points', 'uma', 'score_tie_policy', 'champion_tiebreak_policy', 'rules_version', 'rules_source', 'oka_override']}
        old = SimpleNamespace(**t_fields, oka=derive_oka(t.starting_points, t.return_points) if t.oka_override is None else t.oka_override)
        frozen = rules(old)
        r = model('tournaments.TournamentRound').create(tournament=t, round_number=1, generated_by=admin, generation_snapshot={'rules': frozen, 'source_versions': []})
        fixed = model('tournaments.TournamentTable').create(tournament=t, ordinal=1)
        table = model('tournaments.RoundTable').create(round=r, table_number=1, tournament_table=fixed, machine_snapshot={'machine_id': machine.pk, 'machine_no': '902'})
        for p, wind in zip(entries, ['east', 'south', 'west', 'north']):
            model('tournaments.RoundSeat').create(round=r, table=table, participant=p, seat_wind=wind)
        points = {str(p.pk): raw for p, raw in zip(entries, [40000, 30000, 20000, 10000])}
        scores = score(old, points)
        result = model('tournaments.TableResult').create(table=table, status='confirmed', version=2, points=points, scores=scores, rule_snapshot=frozen, edited_by=admin, confirmed_by=admin, confirmed_at=now)
        before_points = {str(p.pk): raw for p, raw in zip(entries, [35000, 35000, 20000, 10000])}
        common = {'table_id': table.pk, 'status': 'confirmed', 'rules': frozen, 'edited_by': admin.pk, 'edited_at': now.isoformat(), 'confirmed_by': admin.pk, 'confirmed_at': now.isoformat()}
        model('tournaments.TableResultCorrection').create(result=result, from_version=1, to_version=2, before_snapshot={**common, 'points': before_points, 'scores': score(old, before_points), 'version': 1}, after_snapshot={**common, 'points': points, 'scores': scores, 'version': 2}, corrected_by=admin, reason='旧阶段隔离QA更正记录')
        released = state == 'completed'
        allocation = model('tournaments.MachineAllocation').create(table=table, machine=machine, machine_no_snapshot='902', allocated_by=admin, status='released' if released else 'active', released_by=admin if released else None, released_at=now if released else None, release_reason='旧QA已释放' if released else '')
        model('tournaments.TournamentMachineReservation').create(table=fixed, machine=machine, legacy_allocation=allocation, machine_no_snapshot='902', created_by=admin, status='released' if released else 'active', released_by=admin if released else None, released_at=now if released else None, reason='原始预留原因', release_reason='旧QA已释放' if released else '')
        values = {'status': state, 'started_at': now, 'resource_state': 'fixed', 'first_round_order': [p.pk for p in entries], 'order_source': 'persisted_shuffle_v1'}
        if released:
            values.update(completed_at=now, completed_by=admin, champion_id=entries[0].pk, final_snapshot={'rules': frozen, 'champion_id': entries[0].pk, 'standings': [{'participant_id': row['participant_id'], 'rank': row['rank'], 'total': row['score']} for row in scores]})
        model('tournaments.Tournament').filter(pk=t.pk).update(**values)
        expected[t.pk] = frozen
    baseline = build_manifest(connection)
    if baseline['result'] != 'PASS': raise AssertionError('Original QA fixture invalid')
    if before_upgrade: before_upgrade(baseline)
    executor = MigrationExecutor(connection)
    # Keep the historical 0009 rehearsal scoped to 0009 after later upgrades exist.
    targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] != 'tournaments'] + [('tournaments', '0009_pairing_strategies')]
    executor.migrate(targets)
    projection = build_manifest(connection, baseline)
    if projection['result'] != 'PASS': raise AssertionError('0009 changed original fields or identities')
    for t in Tournament.objects.using(connection.alias).filter(pk__in=expected):
        if (t.pairing_strategy, t.table_bonus_policy, t.ranked_table_bonuses) != ('legacy_v1', 'none', ['0'] * 4): raise AssertionError('Legacy rules falsely opted into new pairing')
        for r in t.rounds.all():
            for table in r.tables.all():
                if table.base_bonus != '0' or table.bonus_source != 'legacy_zero': raise AssertionError('Legacy table received a bonus')
                if score(t, table.result.points, table=table) != table.result.scores or rules(t, table=table) != expected[t.pk]: raise AssertionError('Legacy scores or rule semantics changed')
    current = build_manifest(connection)
    executor = MigrationExecutor(connection); executor.migrate(targets)
    if build_manifest(connection, current)['result'] != 'PASS': raise AssertionError('Rerun changed data')
    return {'result': 'PASS', 'vendor': connection.vendor, 'legacy_tournaments': 2, 'legacy_results': 2, 'legacy_corrections': 2, 'original_columns_unchanged': True, 'legacy_zero_bonus': True, 'legacy_rule_snapshots_unchanged': True, 'idempotent_rerun': True, 'additions': projection['additions']}
