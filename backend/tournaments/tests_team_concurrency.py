from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TransactionTestCase

from machines.services import create_machine
from players.services import create_player
from . import team_services as svc
from .competition_services import correct_result, write_result
from .models import Tournament, TeamAuditRecord, TeamMatchPlan
from .services import TournamentConflict


class TeamConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='team_parallel_admin', is_staff=True)
        self.players = [create_player(f'并发成员{i}') for i in range(8)]
        self.machine = create_machine({'name': '并发测试桌'})
        self.t = svc.create_team_tournament(self.admin, {'name': '团队并发', 'schedule_mode': 'free', 'total_matches': 1,
            'teams': [{'name': f'队{i}', 'player_ids': [p.pk for p in self.players[i * 2:i * 2 + 2]]} for i in range(4)]})

    def race(self, operations):
        barrier = Barrier(len(operations))
        def execute(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                operation()
                return 'ok'
            except TournamentConflict as error:
                return error.default_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            return list(pool.map(execute, operations))

    def prepare(self):
        preview = svc.preview_schedule(self.t.pk, self.admin)
        svc.generate_schedule(self.t.pk, self.admin, preview['token'])
        self.t.refresh_from_db()
        plan = svc.plan_query(self.t).get()
        teams = svc.roster(self.t)
        svc.update_plan(self.t.pk, plan.pk, self.admin, version=plan.version,
                        lineup=[{'team_id': team['id'], 'member_id': team['members'][0]['id']} for team in teams], captain_supplied=True)
        plan.refresh_from_db()
        svc.confirm_plans(self.t.pk, self.admin, [{'match_id': plan.pk, 'version': plan.version}])
        svc.start_team_tournament(self.t.pk, user=self.admin)
        return plan

    def test_same_draft_revision_commits_once(self):
        result = self.race([lambda: svc.update_team_tournament(self.t.pk, {'name': '甲'}, user=self.admin, revision=0),
                            lambda: svc.update_team_tournament(self.t.pk, {'name': '乙'}, user=self.admin, revision=0)])
        self.assertEqual(result.count('ok'), 1, result)
        self.assertEqual(TeamAuditRecord.objects.filter(tournament=self.t, action='draft_saved').count(), 1)

    def test_same_plan_version_and_confirmation_each_commit_once(self):
        preview = svc.preview_schedule(self.t.pk, self.admin); svc.generate_schedule(self.t.pk, self.admin, preview['token'])
        self.t.refresh_from_db()
        plan = svc.plan_query(self.t).get()
        lineup = [{'team_id': team['id'], 'member_id': team['members'][0]['id']} for team in svc.roster(self.t)]
        result = self.race([lambda: svc.update_plan(self.t.pk, plan.pk, self.admin, version=1, lineup=lineup, captain_supplied=True)] * 2)
        self.assertEqual(result.count('ok'), 1, result)
        plan.refresh_from_db()
        source = [{'match_id': plan.pk, 'version': plan.version}]
        result = self.race([lambda: svc.confirm_plans(self.t.pk, self.admin, source)] * 2)
        self.assertEqual(result.count('ok'), 1, result)
        self.assertEqual(TeamAuditRecord.objects.filter(tournament=self.t, action='plans_confirmed').count(), 1)

    def test_duplicate_batch_preview_starts_only_one_actual_batch(self):
        self.prepare()
        preview = svc.preview_batch(self.t.pk, self.admin, [self.machine.pk])
        result = self.race([lambda: svc.start_batch(self.t.pk, self.admin, preview['token'])] * 2)
        self.assertEqual(result.count('ok'), 1, result)
        self.assertEqual(Tournament.objects.get(pk=self.t.pk).rounds.count(), 1)
        self.assertEqual(TeamMatchPlan.objects.filter(tournament=self.t, status='started').count(), 1)

    def test_result_correction_vs_finish_never_changes_completed_snapshot(self):
        self.prepare()
        preview = svc.preview_batch(self.t.pk, self.admin, [self.machine.pk]); batch = svc.start_batch(self.t.pk, self.admin, preview['token'])
        table = batch.tables.get()
        ids = list(table.seats.values_list('participant_id', flat=True))
        values = [{'participant_id': pk, 'raw_points': raw} for pk, raw in zip(ids, [40000, 30000, 20000, 10000])]
        write_result(table.pk, self.admin, 0, points=values, confirm=True)
        current = svc.workspace(Tournament.objects.get(pk=self.t.pk))
        sources = {key: current[key] for key in ('source_versions', 'roster_snapshot', 'plan_sources')}
        changed = [{'participant_id': pk, 'raw_points': raw} for pk, raw in zip(ids, [41000, 30000, 20000, 9000])]
        result = self.race([lambda: correct_result(table.pk, self.admin, 1, points=changed), lambda: svc.finish_team(self.t.pk, self.admin, sources)])
        self.assertTrue(set(result) <= {'ok', 'tournament_busy', 'stale_standings', 'tournament_not_started'}, result)
        self.t.refresh_from_db()
        if self.t.status != 'completed':
            current = svc.workspace(self.t)
            svc.finish_team(self.t.pk, self.admin, {key: current[key] for key in ('source_versions', 'roster_snapshot', 'plan_sources')})
            self.t.refresh_from_db()
        snapshot = self.t.final_snapshot
        self.assertEqual(svc.workspace(self.t)['team_standings'], snapshot['team_standings'])
        self.assertFalse(self.t.fixed_tables.filter(reservations__status='active').exists())
