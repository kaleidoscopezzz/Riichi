"""0010 -> team migrations: populated original-column projection and defaults."""
from pathlib import Path

from django.db.migrations.executor import MigrationExecutor

from .schema_manifest import build_manifest

BEFORE_TEAMS = [('tournaments', '0010_event_flow'), ('machines', '0003_remove_mahjongmachine_machine_active_capacity_slot'), ('sessions', '0001_initial')]


def rehearse_team_migrations(connection, *, before_upgrade=None):
    name = str(connection.settings_dict['NAME'])
    root = (Path(__file__).resolve().parents[1] / '.verification').resolve()
    if not (connection.vendor == 'sqlite' and (name == ':memory:' or Path(name).resolve().is_relative_to(root)) or connection.vendor == 'postgresql' and name == 'riichi_qa_teams'):
        raise RuntimeError('Team rehearsal accepts only isolated QA databases')
    executor = MigrationExecutor(connection)
    if executor.migration_plan(BEFORE_TEAMS) or ('tournaments', '0011_team_competitions') in executor.loader.applied_migrations:
        raise RuntimeError('Team rehearsal requires the exact pre-team 0010 state')
    baseline = build_manifest(connection)
    if baseline['result'] != 'PASS': raise AssertionError('Original fixture integrity failed')
    if before_upgrade: before_upgrade(baseline)
    targets = executor.loader.graph.leaf_nodes()
    executor.migrate(targets)
    projection = build_manifest(connection, baseline)
    if projection['result'] != 'PASS':
        raise AssertionError('Team migrations changed original data/types/relations: ' + ', '.join(projection['differences']))
    apps = executor.loader.project_state(targets).apps
    query = lambda model: apps.get_model('tournaments', model).objects.using(connection.alias)
    if query('Tournament').exclude(competition_type='individual', champion_team__isnull=True).exists():
        raise AssertionError('Legacy events changed mode or gained a team champion')
    if query('TournamentRound').exclude(competition_type='individual').exists():
        raise AssertionError('Legacy rounds changed type')
    if query('LotteryRecord').exclude(entity_type='participant', roster_snapshot=[], plan_sources=[]).exists():
        raise AssertionError('Legacy lottery source/entity changed')
    names = ('TournamentTeam', 'TeamMember', 'TeamCompetitionSettings', 'TeamStage', 'TeamStageRepresentative', 'TeamMatchPlan', 'TeamAuditRecord')
    if any(query(name).exists() for name in names): raise AssertionError('Migration invented team records')
    current = build_manifest(connection)
    executor = MigrationExecutor(connection); executor.migrate(targets)
    if build_manifest(connection, current)['result'] != 'PASS': raise AssertionError('Rerun changed data')
    return {'result': 'PASS', 'vendor': connection.vendor, 'original_columns_types_rows_and_keys_unchanged': True,
            'legacy_individual_defaults': True, 'no_team_records_invented': True, 'legacy_lotteries_participant': True,
            'idempotent_rerun': True, 'additions': projection['additions']}
