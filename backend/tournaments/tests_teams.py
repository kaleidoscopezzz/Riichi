from collections import Counter
from copy import deepcopy
from fractions import Fraction
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, TestCase
from django.utils import timezone

from machines.services import create_machine, change_machine
from players.services import create_player
from .models import Tournament, TournamentParticipant, TeamMatchPlan, TeamAuditRecord, LotteryRecord, TableResult
from .scoring import unpack
from . import team_services as svc
from . import competition_services as individual


class TeamApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_user(username='team_test_admin', is_staff=True)
        cls.players = [create_player(f'团队测试选手{i + 1}') for i in range(80)]
        cls.machines = [create_machine({'name': f'团队物理桌{i + 1}'}) for i in range(4)]

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.admin)
        self.csrf = self.client.get('/api/v1/auth/csrf/').json()['data']['csrf_token']

    def write(self, path, body, method='post'):
        return getattr(self.client, method)('/api/v1/' + path, body, content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)

    def read(self, path):
        response = self.client.get('/api/v1/' + path)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()['data']

    def expect_data(self, response, code=200):
        self.assertEqual(response.status_code, code, response.content)
        return response.json()['data']

    def create(self, teams=4, members=2, mode='free', total=4, cycles=1, games=2, oka='0'):
        counts = members if isinstance(members, list) else [members] * teams
        offset = 0; roster = []
        for i, count in enumerate(counts):
            roster.append({'name': f'队伍{i + 1}', 'player_ids': [p.pk for p in self.players[offset:offset + count]]})
            offset += count
        response = self.write('tournaments/', {'competition_type': 'team', 'name': '真实团队API测试', 'starting_points': 25000,
            'return_points': 30000, 'uma': ['30', '10', '-10', '-30'], 'oka_override': oka,
            'schedule_mode': mode, 'total_matches': total if mode == 'free' else None,
            'positions': ['先锋', '次峰', '中间', '副将', '大将'], 'games_per_position': games,
            'cycles': cycles, 'teams': roster})
        return self.expect_data(response, 201)

    def plans(self, tid, stage=None):
        rows = []; page = 1
        while True:
            data = self.read(f'tournaments/{tid}/team/plans/?page={page}' + (f'&stage={stage}' if stage else ''))
            rows.extend(data['results'])
            if not data['has_next']: return rows
            page += 1

    def generate(self, tid):
        preview = self.expect_data(self.write(f'tournaments/{tid}/team/schedule/preview/', {}))
        self.expect_data(self.write(f'tournaments/{tid}/team/schedule/generate/', {'token': preview['token'], 'confirmed': True}), 201)
        return self.plans(tid)

    def prepare_free(self, row, *, alternating=False):
        tid = row['id']; plans = self.generate(tid)
        teams = {team['id']: team for team in self.read(f'tournaments/{tid}/')['teams']}
        updated = []
        for p in plans:
            updated.append(self.expect_data(self.write(f"tournaments/{tid}/team/plans/{p['id']}/", {'version': p['version'],
                'lineup': [{'team_id': team_id, 'member_id': teams[team_id]['members'][(p['match_number'] - 1) % len(teams[team_id]['members']) if alternating else 0]['id']}
                           for team_id in p['team_ids']], 'captain_supplied': True}, 'put')))
        self.expect_data(self.write(f'tournaments/{tid}/team/plans/confirm/', {'confirmed': True,
            'plan_sources': [{'match_id': p['id'], 'version': p['version']} for p in updated]}))
        self.expect_data(self.write(f'tournaments/{tid}/start/', {}))
        return self.plans(tid)

    def set_stage(self, tid, stage_id, member_index=0):
        t = self.read(f'tournaments/{tid}/')
        for team in t['teams']:
            t = self.read(f'tournaments/{tid}/')
            self.expect_data(self.write(f'tournaments/{tid}/team/stages/{stage_id}/representative/', {
                'revision': t['revision'], 'team_id': team['id'], 'member_id': team['members'][member_index % len(team['members'])]['id'],
                'captain_supplied': True}, 'put'))
        plans = self.plans(tid, stage_id)
        self.expect_data(self.write(f'tournaments/{tid}/team/plans/confirm/', {'confirmed': True,
            'plan_sources': [{'match_id': p['id'], 'version': p['version']} for p in plans]}))

    def batch(self, tid, machines=None):
        payload = {'machine_ids': [m.pk for m in (machines or self.machines[:1])]} if not Tournament.objects.get(pk=tid).rounds.exists() else {}
        preview = self.expect_data(self.write(f'tournaments/{tid}/team/batches/preview/', payload))
        batch = self.expect_data(self.write(f'tournaments/{tid}/team/batches/start/', {'token': preview['token'], 'confirmed': True}), 201)
        return batch

    def confirm_batch(self, tid, batch, *, ties=False):
        teams = self.read(f'tournaments/{tid}/')['teams']
        team_of = {m['participant_id']: team['id'] for team in teams for m in team['members']}
        order = {team['id']: i for i, team in enumerate(teams)}
        for table in batch['tables']:
            ids = sorted((s['participant_id'] for s in table['seats']), key=lambda pk: order[team_of[pk]])
            points = [{'participant_id': pk, 'raw_points': 25000 if ties else value} for pk, value in zip(ids, [40000, 30000, 20000, 10000])]
            self.expect_data(self.write(f"round-tables/{table['id']}/result/confirm/", {'version': 0, 'points': points}))

    def resolve(self, tid):
        ws = self.read(f'tournaments/{tid}/workspace/')
        for group in ws['unresolved_groups']:
            lottery = self.expect_data(self.write(f'tournaments/{tid}/lotteries/', {'entity_type': 'team', 'members': group, 'order': group[::-1],
                'method': '现场团队纸签', 'description': '隔离QA完整公开顺序', 'drawn_at': timezone.now().isoformat(),
                'source_versions': ws['source_versions'], 'roster_snapshot': ws['roster_snapshot'], 'plan_sources': ws['plan_sources']}), 201)
            self.expect_data(self.write(f"tournaments/{tid}/lotteries/{lottery['id']}/confirm/", {'confirmed': True}))

    def complete(self, tid):
        self.resolve(tid)
        ws = self.read(f'tournaments/{tid}/workspace/')
        return self.expect_data(self.write(f'tournaments/{tid}/complete/', {'confirmed': True,
            'source_versions': ws['source_versions'], 'roster_snapshot': ws['roster_snapshot'], 'plan_sources': ws['plan_sources']}))

    def test_create_variable_rosters_over_sixteen_and_identity_snapshot(self):
        row = self.create(6, [1, 7, 2, 5, 6, 3], total=6)
        self.assertEqual(row['participant_count'], 24)
        self.assertIsNone(row['round_count'])
        self.assertEqual(len(row['teams']), 6)
        self.assertEqual([len(t['members']) for t in row['teams']], [1, 7, 2, 5, 6, 3])
        self.assertTrue(all('username' not in str(team) for team in row['teams']))
        self.generate(row['id'])
        self.expect_data(self.write(f"tournaments/{row['id']}/start/", {}))
        self.players[0].nickname = '后来修改档案'; self.players[0].save()
        current = self.read(f"tournaments/{row['id']}/")
        self.assertEqual(current['teams'][0]['members'][0]['display_name'], '团队测试选手1')

    def test_free_schedule_full_api_closure_and_team_sum_not_member_average(self):
        row = self.create(5, [1, 2, 3, 4, 5], total=5, oka=None)
        self.prepare_free(row)
        for _ in range(5): self.confirm_batch(row['id'], self.batch(row['id']))
        result = self.complete(row['id'])
        self.assertEqual(len(result['team_standings']), 5)
        self.assertEqual(result['champion_team_id'], row['teams'][0]['id'])
        self.assertIsNone(result['champion_id'])
        self.assertEqual({team['confirmed_matches'] for team in result['team_standings']}, {4})
        for team in result['team_standings']:
            self.assertEqual(unpack(team['total']), sum((unpack(p['total']) for p in team['contributions']), Fraction()))
        self.assertEqual(sum((unpack(t['total']) for t in result['team_standings']), Fraction()), 0)
        t = Tournament.objects.get(pk=row['id'])
        self.assertEqual(t.champion_team_id, result['champion_team_id'])
        self.assertFalse(t.fixed_tables.filter(reservations__status='active').exists())
        current = self.read(f"tournaments/{row['id']}/workspace/")
        self.assertEqual(current['team_standings'], result['team_standings'])
        self.assertEqual(current['roster_snapshot'], result['roster_snapshot'])
        self.assertEqual(current['mapping'], result['mapping'])
        self.assertEqual(len(current['mapping']), 1)
        self.assertEqual(current['resource_state'], 'fixed')
        self.assertEqual(current['revision'], t.revision)
        self.assertEqual(current['lotteries'], result['lotteries'])
        self.assertEqual(current['stages'], [])

    def test_positions_ten_stages_twenty_batches_and_next_cycle_representatives(self):
        row = self.create(4, 2, mode='positions', cycles=2)
        self.generate(row['id'])
        self.expect_data(self.write(f"tournaments/{row['id']}/start/", {}))
        ws = self.read(f"tournaments/{row['id']}/workspace/")
        self.assertEqual(len(ws['stages']), 10)
        for stage in ws['stages']:
            self.set_stage(row['id'], stage['id'], stage['cycle'] - 1)
            for _ in range(2):
                batch = self.batch(row['id'])
                self.confirm_batch(row['id'], batch)
        result = self.complete(row['id'])
        self.assertEqual(result['match_count'], 20)
        self.assertEqual(Tournament.objects.get(pk=row['id']).rounds.count(), 20)
        self.assertEqual({row['confirmed_matches'] for row in result['team_standings']}, {20})
        self.assertTrue(all({m['position_label'] for m in team['matches']} == {'先锋', '次峰', '中间', '副将', '大将'} for team in result['team_standings']))

    def test_five_and_seven_teams_two_games_rejected_four_valid_without_auto_rewriting(self):
        for count in (5, 7):
            row = self.create(count, 1, mode='positions', games=2)
            ws = self.read(f"tournaments/{row['id']}/workspace/")
            self.assertEqual(ws['match_count'], 0)
            self.assertFalse(ws['ready'])
            response = self.write(f"tournaments/{row['id']}/team/schedule/preview/", {})
            self.assertEqual(response.status_code, 400)
            self.assertIn('4场', str(response.json()))
            self.assertEqual(self.read(f"tournaments/{row['id']}/")['team_settings']['games_per_position'], 2)
            self.assertEqual(TeamMatchPlan.objects.filter(tournament_id=row['id']).count(), 0)
            self.expect_data(self.write(f"tournaments/{row['id']}/", {'games_per_position': 4, 'revision': row['revision']}, 'patch'))
            plans = self.generate(row['id'])
            self.assertEqual(len(plans), count * 5)
            self.assertTrue(all(len(set(p['team_ids'])) == 4 for p in plans))

    def test_one_member_can_hold_all_positions_without_roster_size_five_requirement(self):
        row = self.create(4, 1, mode='positions')
        self.generate(row['id'])
        self.expect_data(self.write(f"tournaments/{row['id']}/start/", {}))
        ws = self.read(f"tournaments/{row['id']}/workspace/")
        self.set_stage(row['id'], ws['stages'][0]['id'])
        batch = self.batch(row['id'])
        self.confirm_batch(row['id'], batch)
        self.confirm_batch(row['id'], self.batch(row['id']))
        self.set_stage(row['id'], ws['stages'][1]['id'])
        self.assertEqual(len(self.batch(row['id'])['tables'][0]['seats']), 4)

    def test_missing_lineup_is_draft_only_and_foreign_members_rejected(self):
        row = self.create(); plans = self.generate(row['id'])
        first = plans[0]
        response = self.write(f"tournaments/{row['id']}/team/plans/confirm/", {'confirmed': True,
            'plan_sources': [{'match_id': first['id'], 'version': first['version']}]})
        self.assertEqual(response.status_code, 400)
        other = row['teams'][1]['members'][0]['id']
        response = self.write(f"tournaments/{row['id']}/team/plans/{first['id']}/", {'version': first['version'],
            'lineup': [{'team_id': row['teams'][0]['id'], 'member_id': other}], 'captain_supplied': True}, 'put')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(TeamMatchPlan.objects.get(pk=first['id']).version, first['version'])

    def test_same_member_cannot_play_parallel_but_same_team_distinct_members_can(self):
        row = self.create(total=4)
        self.prepare_free(row, alternating=False)
        first = self.batch(row['id'], self.machines[:4])
        self.assertEqual(len(first['tables']), 1)
        self.confirm_batch(row['id'], first)
        second = self.create(total=4)
        self.prepare_free(second, alternating=True)
        batch = self.batch(second['id'], self.machines[:4])
        self.assertEqual(len(batch['tables']), 2)
        ids = [s['participant_id'] for table in batch['tables'] for s in table['seats']]
        self.assertEqual(len(ids), len(set(ids)))

    def test_stage_cannot_advance_early_and_representative_locked_for_remaining_games(self):
        row = self.create(mode='positions'); self.generate(row['id'])
        self.expect_data(self.write(f"tournaments/{row['id']}/start/", {}))
        ws = self.read(f"tournaments/{row['id']}/workspace/")
        self.set_stage(row['id'], ws['stages'][1]['id'])
        self.assertEqual(self.write(f"tournaments/{row['id']}/team/batches/preview/", {'machine_ids': [self.machines[0].pk]}).status_code, 409)
        self.set_stage(row['id'], ws['stages'][0]['id'])
        batch = self.batch(row['id'])
        current = self.read(f"tournaments/{row['id']}/")
        response = self.write(f"tournaments/{row['id']}/team/stages/{ws['stages'][0]['id']}/representative/", {
            'revision': current['revision'], 'team_id': row['teams'][0]['id'], 'member_id': row['teams'][0]['members'][1]['id'],
            'captain_supplied': True}, 'put')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error']['code'], 'stage_representative_locked')
        self.assertEqual(self.write(f"tournaments/{row['id']}/team/batches/preview/", {}).status_code, 409)
        self.confirm_batch(row['id'], batch)
        self.assertEqual(len(self.batch(row['id'])['tables']), 1)
        progress = self.read(f"tournaments/{row['id']}/workspace/")['stages'][0]['representatives']
        self.assertEqual({(r['confirmed_matches'], r['planned_matches']) for r in progress}, {(1, 2)})

    def test_confirmed_plan_requires_audited_withdrawal_and_stale_version_cannot_overwrite(self):
        row = self.create(); self.prepare_free(row)
        p = self.plans(row['id'])[0]
        self.assertEqual(self.write(f"tournaments/{row['id']}/team/plans/{p['id']}/", {'version': p['version'], 'lineup': []}, 'put').status_code, 409)
        self.expect_data(self.write(f"tournaments/{row['id']}/team/plans/{p['id']}/withdraw/", {'version': p['version'], 'confirmed': True, 'reason': '队长更换未开场成员'}))
        self.assertEqual(self.write(f"tournaments/{row['id']}/team/plans/{p['id']}/", {'version': p['version'], 'lineup': []}, 'put').status_code, 409)
        self.assertTrue(TeamAuditRecord.objects.filter(tournament_id=row['id'], action='plan_withdrawn', reason='队长更换未开场成员').exists())

    def test_score_correction_updates_team_totals_but_preserves_all_generated_memberships(self):
        row = self.create(total=2); self.prepare_free(row)
        first = self.batch(row['id']); self.confirm_batch(row['id'], first)
        second = self.batch(row['id'])
        table = first['tables'][0]; seats_before = deepcopy(second['tables'][0]['seats'])
        ids = [s['participant_id'] for s in table['seats']]
        points = [{'participant_id': pid, 'raw_points': raw} for pid, raw in zip(ids, [900000, 30000, 20000, -850000])]
        self.expect_data(self.write(f"round-tables/{table['id']}/result/correct/", {'version': 1, 'points': points, 'reason': '核对早场点数'}))
        self.assertEqual(self.read(f"tournaments/{row['id']}/team/batches/")['results'][0]['tables'][0]['seats'], seats_before)
        ws = self.read(f"tournaments/{row['id']}/workspace/")
        self.assertEqual(sum(team['confirmed_matches'] for team in ws['team_standings']), 4)
        self.assertTrue(any(unpack(t['total']) > 800 for t in ws['team_standings']))
        self.assertEqual(len(self.read(f"round-tables/{table['id']}/result/corrections/")['corrections']), 1)

    def test_drafts_not_counted_and_three_exact_thirds_sum_to_fifty(self):
        row = self.create(total=3, oka=None); self.prepare_free(row)
        target = row['teams'][0]['members'][0]['participant_id']
        for i in range(3):
            batch = self.batch(row['id']); table = batch['tables'][0]
            ids = [s['participant_id'] for s in table['seats']]
            loser = next(pid for pid in ids if pid != target)
            points = [{'participant_id': pid, 'raw_points': 10000 if pid == loser else 30000} for pid in ids]
            if i == 0:
                self.expect_data(self.write(f"round-tables/{table['id']}/result/", {'version': 0, 'points': points}, 'put'))
                self.assertEqual(self.read(f"tournaments/{row['id']}/workspace/")['completed_matches'], 0)
            self.expect_data(self.write(f"round-tables/{table['id']}/result/confirm/", {'version': 1 if i == 0 else 0, 'points': points}))
        ws = self.read(f"tournaments/{row['id']}/workspace/")
        team = next(t for t in ws['team_standings'] if t['team_id'] == row['teams'][0]['id'])
        self.assertEqual(unpack(team['total']), 50)
        self.assertEqual(unpack(team['contributions'][0]['total']), 50)
        others = [pid for pid in ids if pid != target]
        points = [{'participant_id': target, 'raw_points': 40000}] + [
            {'participant_id': pid, 'raw_points': raw} for pid, raw in zip(others, [30000, 20000, 10000])]
        preview = self.expect_data(self.write(f"round-tables/{table['id']}/result/preview/", {'version': 1, 'points': points}))
        change = next(c for c in preview['team_changes'] if c['participant_id'] == target)
        self.assertEqual(unpack(change['confirmed_total']), 50)
        self.assertEqual(unpack(change['previous_score']), Fraction(50, 3))
        self.assertEqual(unpack(change['score_change']), Fraction(130, 3))
        self.assertEqual(unpack(change['projected_total']), Fraction(280, 3))
        self.assertEqual(preview['team_source_versions'], ws['source_versions'])
        self.assertEqual(TableResult.objects.get(table_id=table['id']).version, 1)
        self.assertEqual(self.read(f"tournaments/{row['id']}/workspace/")['team_standings'], ws['team_standings'])

    def test_team_lottery_and_individual_auxiliary_ties_have_distinct_scope(self):
        row = self.create(total=1); self.prepare_free(row)
        self.confirm_batch(row['id'], self.batch(row['id']), ties=True)
        ws = self.read(f"tournaments/{row['id']}/workspace/")
        group = ws['unresolved_groups'][0]
        self.assertEqual(len(group), 4)
        body = {'entity_type': 'team', 'members': group, 'order': group[::-1], 'method': '公开纸签',
                'description': '团队冠军公开顺序', 'drawn_at': timezone.now().isoformat(),
                'source_versions': ws['source_versions'], 'roster_snapshot': ws['roster_snapshot'], 'plan_sources': ws['plan_sources']}
        lottery = self.expect_data(self.write(f"tournaments/{row['id']}/lotteries/", body), 201)
        self.assertEqual(self.write(f"tournaments/{row['id']}/lotteries/", body).status_code, 409)
        self.assertEqual(self.write(f"tournaments/{row['id']}/lotteries/", body | {'entity_type': 'participant'}).status_code, 400)
        self.expect_data(self.write(f"tournaments/{row['id']}/lotteries/{lottery['id']}/confirm/", {'confirmed': True}))
        final = self.complete(row['id'])
        self.assertEqual(final['champion_team_id'], group[-1])
        self.assertEqual({p['rank'] for p in final['standings'] if p['confirmed_rounds']}, {1})
        self.assertTrue(all(p['rank'] is None and p['rounds'] == [] for p in final['standings'] if not p['confirmed_rounds']))
        self.assertEqual(final['lottery_ids'], [lottery['id']])

    def test_stale_batch_preview_and_final_sources_rejected_after_correcting_scores(self):
        row = self.create(total=2); self.prepare_free(row)
        first = self.batch(row['id']); self.confirm_batch(row['id'], first)
        preview = self.expect_data(self.write(f"tournaments/{row['id']}/team/batches/preview/", {}))
        table = first['tables'][0]
        points = [{'participant_id': s['participant_id'], 'raw_points': 25000} for s in table['seats']]
        self.expect_data(self.write(f"round-tables/{table['id']}/result/correct/", {'version': 1, 'points': points}))
        response = self.write(f"tournaments/{row['id']}/team/batches/start/", {'token': preview['token'], 'confirmed': True})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error']['code'], 'stale_team_preview')

    def test_role_and_personal_operations_cannot_be_used_for_team_elimination_or_round_creation(self):
        row = self.create(); self.prepare_free(row)
        self.assertEqual(self.write(f"tournaments/{row['id']}/rounds/", {'round_number': 1, 'machine_ids': [self.machines[0].pk]}).status_code, 409)
        self.assertEqual(self.write(f"tournaments/{row['id']}/eliminations/", {'round_number': 1, 'confirmed': True, 'participant_ids': [1, 2, 3, 4],
            'source_versions': [], 'participant_statuses': [{'participant_id': i, 'eliminated_after_round': None} for i in (1, 2, 3, 4)]}).status_code, 409)
        paths = [f"tournaments/{row['id']}/team/schedule/preview/", f"tournaments/{row['id']}/team/batches/preview/", f"tournaments/{row['id']}/team/plans/confirm/"]
        for path in paths:
            self.assertEqual(self.client.post('/api/v1/' + path, {}, content_type='application/json').status_code, 403)
            anonymous = Client(enforce_csrf_checks=True)
            self.assertEqual(anonymous.post('/api/v1/' + path, {}, content_type='application/json').status_code, 403)
        self.client.force_login(self.players[0].user)
        self.assertEqual(self.client.get(f"/api/v1/tournaments/{row['id']}/workspace/").status_code, 403)

    def test_representative_and_batch_failures_rollback_and_completed_tournament_stays_read_only(self):
        row = self.create(total=1); self.prepare_free(row)
        preview = self.expect_data(self.write(f"tournaments/{row['id']}/team/batches/preview/", {'machine_ids': [self.machines[0].pk]}))
        with patch('tournaments.team_services.RoundSeat.objects.bulk_create', side_effect=IntegrityError('injected')):
            self.assertEqual(self.write(f"tournaments/{row['id']}/team/batches/start/", {'token': preview['token'], 'confirmed': True}).status_code, 409)
        t = Tournament.objects.get(pk=row['id'])
        self.assertEqual(t.rounds.count(), 0)
        self.assertEqual(t.fixed_tables.count(), 0)
        self.assertFalse(t.team_matches.exclude(status='confirmed').exists())
        batch = self.batch(row['id']); self.confirm_batch(row['id'], batch)
        final = self.complete(row['id'])
        self.assertEqual(self.read(f"tournaments/{row['id']}/workspace/")['team_standings'], final['team_standings'])
        self.assertEqual(self.write(f"tournaments/{row['id']}/team/schedule/reset/", {'revision': Tournament.objects.get(pk=row['id']).revision,
            'confirmed': True, 'reason': '不能覆盖完赛'}).status_code, 409)

    def test_each_team_captain_source_required_for_stage_and_bulk_representatives_atomic(self):
        row = self.create(mode='positions'); self.generate(row['id'])
        stage = self.read(f"tournaments/{row['id']}/workspace/")['stages'][0]
        for i, team in enumerate(row['teams']):
            current = self.read(f"tournaments/{row['id']}/")
            self.expect_data(self.write(f"tournaments/{row['id']}/team/stages/{stage['id']}/representative/", {
                'revision': current['revision'], 'team_id': team['id'], 'member_id': team['members'][0]['id'], 'captain_supplied': i != 0}, 'put'))
        plans = self.plans(row['id'], stage['id'])
        self.assertTrue(all(not p['captain_supplied'] for p in plans))
        p = plans[0]
        self.expect_data(self.write(f"tournaments/{row['id']}/team/plans/{p['id']}/", {'version': p['version'], 'captain_supplied': True}, 'put'))
        plans = self.plans(row['id'], stage['id'])
        self.assertTrue(all(not p['captain_supplied'] for p in plans))
        self.assertEqual(self.write(f"tournaments/{row['id']}/team/plans/confirm/", {'confirmed': True,
            'plan_sources': [{'match_id': p['id'], 'version': p['version']} for p in plans]}).status_code, 400)
        before = deepcopy(self.read(f"tournaments/{row['id']}/workspace/")['stages'][0]['representatives'])
        current = self.read(f"tournaments/{row['id']}/")
        bad = [{'team_id': row['teams'][0]['id'], 'member_id': row['teams'][0]['members'][1]['id']},
               {'team_id': row['teams'][1]['id'], 'member_id': row['teams'][0]['members'][0]['id']}]
        self.assertEqual(self.write(f"tournaments/{row['id']}/team/stages/{stage['id']}/representatives/", {
            'revision': current['revision'], 'representatives': bad, 'captain_supplied': True}, 'put').status_code, 400)
        self.assertEqual(self.read(f"tournaments/{row['id']}/workspace/")['stages'][0]['representatives'], before)

    def test_clear_unstarted_representative_updates_plans_source_and_audit_but_locked_representative_cannot_clear(self):
        row = self.create(mode='positions'); self.generate(row['id'])
        stage_id = self.read(f"tournaments/{row['id']}/workspace/")['stages'][0]['id']
        team = row['teams'][0]
        path = f"tournaments/{row['id']}/team/stages/{stage_id}/representative/"
        current = self.read(f"tournaments/{row['id']}/")
        members = [{'team_id': t['id'], 'member_id': t['members'][0]['id']} for t in row['teams']]
        self.expect_data(self.write(f"tournaments/{row['id']}/team/stages/{stage_id}/representatives/", {
            'revision': current['revision'], 'representatives': members, 'captain_supplied': True}, 'put'))
        before = self.plans(row['id'], stage_id)
        current = self.read(f"tournaments/{row['id']}/")
        self.expect_data(self.write(path, {'revision': current['revision'], 'team_id': team['id'],
            'member_id': None, 'captain_supplied': True}, 'put'))
        stage = self.read(f"tournaments/{row['id']}/workspace/")['stages'][0]
        rep = next(r for r in stage['representatives'] if r['team_id'] == team['id'])
        self.assertIsNone(rep['member_id']); self.assertFalse(rep['captain_supplied'])
        plans = self.plans(row['id'], stage_id)
        self.assertTrue(all(p['lineup'][str(team['id'])] is None and not p['captain_supplied'] for p in plans))
        self.assertEqual([p['version'] for p in plans], [p['version'] + 1 for p in before])
        record = TeamAuditRecord.objects.filter(tournament_id=row['id'], action='representative_updated').latest('id')
        self.assertEqual(record.before_snapshot['member_id'], team['members'][0]['id'])
        self.assertIsNone(record.after_snapshot['member_id'])
        self.assertFalse(record.after_snapshot['captain_supplied'])
        self.set_stage(row['id'], stage_id)
        current = self.read(f"tournaments/{row['id']}/")
        clear = {'revision': current['revision'], 'team_id': team['id'], 'member_id': None, 'captain_supplied': True}
        self.assertEqual(self.write(path, clear, 'put').status_code, 409)
        self.assertTrue(all(p['status'] == 'confirmed' for p in self.plans(row['id'], stage_id)))
        self.expect_data(self.write(path, clear | {'withdraw_confirmed': True, 'reason': '队长撤回未开场代表'}, 'put'))
        self.assertTrue(all(p['status'] == 'draft' and p['confirmed_at'] is None and p['lineup'][str(team['id'])] is None
                            for p in self.plans(row['id'], stage_id)))
        self.set_stage(row['id'], stage_id)
        self.expect_data(self.write(f"tournaments/{row['id']}/start/", {}))
        self.batch(row['id'])
        current = self.read(f"tournaments/{row['id']}/")
        response = self.write(path, clear | {'revision': current['revision'], 'withdraw_confirmed': True,
            'reason': '已开场不能清空'}, 'put')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error']['code'], 'stage_representative_locked')

    def test_reset_schedule_hides_voided_stages_without_removing_history(self):
        row = self.create(mode='positions'); self.generate(row['id'])
        original_stage = self.read(f"tournaments/{row['id']}/workspace/")['stages'][0]
        stage_id = original_stage['id']
        current = self.read(f"tournaments/{row['id']}/")
        self.expect_data(self.write(f"tournaments/{row['id']}/team/stages/{stage_id}/representative/", {
            'revision': current['revision'], 'team_id': row['teams'][0]['id'],
            'member_id': row['teams'][0]['members'][0]['id'], 'captain_supplied': True}, 'put'))
        current = self.read(f"tournaments/{row['id']}/")
        self.expect_data(self.write(f"tournaments/{row['id']}/team/schedule/reset/", {
            'revision': current['revision'], 'confirmed': True, 'reason': '修改草稿场数'}))
        ws = self.read(f"tournaments/{row['id']}/workspace/")
        self.assertEqual(ws['stages'], [])
        self.assertEqual(ws['match_count'], 0)
        self.assertEqual(Tournament.objects.get(pk=row['id']).team_stages.count(), 5)
        self.assertTrue(TeamMatchPlan.objects.filter(tournament_id=row['id'], status='voided').exists())
        tournament = Tournament.objects.get(pk=row['id'])
        before_revision, before_audits = tournament.revision, tournament.team_audits.count()
        before_plans = [svc.plan_snapshot(p) for p in tournament.team_matches.order_by('id')]
        rep = tournament.team_stages.get(pk=stage_id).representatives.get(team_id=row['teams'][0]['id'])
        before_rep = (rep.member_id, rep.captain_supplied)
        body = {'revision': before_revision, 'team_id': row['teams'][0]['id'], 'member_id': None}
        response = self.write(f"tournaments/{row['id']}/team/stages/{stage_id}/representative/", body, 'put')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error']['code'], 'team_stage_inactive')
        response = self.write(f"tournaments/{row['id']}/team/stages/{stage_id}/representatives/", {
            'revision': before_revision, 'representatives': [{'team_id': row['teams'][0]['id'], 'member_id': None}]}, 'put')
        self.assertEqual(response.status_code, 409)
        tournament.refresh_from_db(); rep.refresh_from_db()
        self.assertEqual((rep.member_id, rep.captain_supplied), before_rep)
        self.assertEqual((tournament.revision, tournament.team_audits.count()), (before_revision, before_audits))
        self.assertEqual([svc.plan_snapshot(p) for p in tournament.team_matches.order_by('id')], before_plans)
        self.generate(row['id'])
        new_stage = self.read(f"tournaments/{row['id']}/workspace/")['stages'][0]
        self.assertNotEqual(new_stage['id'], stage_id)
        current = self.read(f"tournaments/{row['id']}/")
        self.expect_data(self.write(f"tournaments/{row['id']}/team/stages/{new_stage['id']}/representative/", {
            'revision': current['revision'], 'team_id': row['teams'][0]['id'],
            'member_id': row['teams'][0]['members'][1]['id'], 'captain_supplied': True}, 'put'))

    def test_team_lottery_void_history_and_final_source_after_correction(self):
        row = self.create(total=1); self.prepare_free(row)
        batch = self.batch(row['id']); self.confirm_batch(row['id'], batch, ties=True)
        ws = self.read(f"tournaments/{row['id']}/workspace/")
        group = ws['unresolved_groups'][0]
        body = {'entity_type': 'team', 'members': group, 'order': group[::-1], 'method': '公开纸签',
                'description': '保留抽签审计', 'drawn_at': timezone.now().isoformat(),
                'source_versions': ws['source_versions'], 'roster_snapshot': ws['roster_snapshot'], 'plan_sources': ws['plan_sources']}
        first = self.expect_data(self.write(f"tournaments/{row['id']}/lotteries/", body), 201)
        path = f"tournaments/{row['id']}/lotteries/{first['id']}/void/"
        self.assertEqual(self.write(path, {'reason': ''}).status_code, 400)
        voided = self.expect_data(self.write(path, {'reason': '顺序录入有误'}))
        self.assertEqual(voided['void_reason'], '顺序录入有误')
        self.assertIsNotNone(voided['voided_at'])
        self.assertEqual(self.write(f"tournaments/{row['id']}/lotteries/{first['id']}/confirm/", {'confirmed': True}).status_code, 409)
        second = self.expect_data(self.write(f"tournaments/{row['id']}/lotteries/", body), 201)
        self.expect_data(self.write(f"tournaments/{row['id']}/lotteries/{second['id']}/confirm/", {'confirmed': True}))
        before = self.read(f"tournaments/{row['id']}/workspace/")
        table = batch['tables'][0]
        points = [{'participant_id': s['participant_id'], 'raw_points': raw} for s, raw in zip(table['seats'], [40000, 30000, 20000, 10000])]
        self.expect_data(self.write(f"round-tables/{table['id']}/result/correct/", {'version': 1, 'points': points, 'reason': '核对终局点数'}))
        stale = self.write(f"tournaments/{row['id']}/complete/", {'confirmed': True, 'source_versions': before['source_versions'],
            'roster_snapshot': before['roster_snapshot'], 'plan_sources': before['plan_sources']})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()['error']['code'], 'stale_standings')
        final = self.complete(row['id'])
        self.assertEqual(final['lottery_ids'], [])
        self.assertEqual(len(final['lotteries']), 2)
        self.assertTrue(all(draw['entity_type'] == 'team' for draw in final['lotteries']))
        self.assertEqual(self.write(f"round-tables/{table['id']}/result/correct/", {'version': 2, 'points': points}).status_code, 409)

    def test_manual_team_groups_require_global_equal_quotas_before_confirmation(self):
        row = self.create(5, 2, total=5)
        self.expect_data(self.write(f"tournaments/{row['id']}/", {'pairing_strategy': 'team_manual_v1', 'revision': row['revision']}, 'patch'))
        plans = self.generate(row['id']); p = plans[0]
        team_by_id = {team['id']: team for team in row['teams']}
        missing = next(pk for pk in team_by_id if pk not in p['team_ids'])
        changed_ids = [missing] + p['team_ids'][1:]
        path = f"tournaments/{row['id']}/team/plans/{p['id']}/"
        changed = self.expect_data(self.write(path, {'version': p['version'], 'team_ids': changed_ids,
            'lineup': [{'team_id': pk, 'member_id': team_by_id[pk]['members'][0]['id']} for pk in changed_ids], 'captain_supplied': True}, 'put'))
        self.assertEqual(self.write(f"tournaments/{row['id']}/team/plans/confirm/", {'confirmed': True,
            'plan_sources': [{'match_id': p['id'], 'version': changed['version']}]}).status_code, 400)
        self.assertEqual(self.read(f"tournaments/{row['id']}/team/plans/{p['id']}/")['team_ids'], changed_ids)
        self.assertEqual(self.write(path, {'version': changed['version'], 'team_ids': [missing] * 4}, 'put').status_code, 400)
        fixed = self.expect_data(self.write(path, {'version': changed['version'], 'team_ids': p['team_ids'],
            'lineup': [{'team_id': pk, 'member_id': team_by_id[pk]['members'][0]['id']} for pk in p['team_ids']], 'captain_supplied': True}, 'put'))
        self.expect_data(self.write(f"tournaments/{row['id']}/team/plans/confirm/", {'confirmed': True,
            'plan_sources': [{'match_id': fixed['id'], 'version': fixed['version']}]}))

    def test_team_and_individual_share_real_machine_maintenance_and_releases_are_scoped(self):
        from .services import create_tournament, mutate_tournament
        personal = create_tournament(self.admin, {'name': '同桌个人赛', 'round_count': 1,
            'participant_ids': [p.pk for p in self.players[:4]]})
        mutate_tournament(personal.pk, start=True)
        individual.generate(personal.pk, self.admin, 1, machine_ids=[self.machines[0].pk])
        row = self.create(total=1); self.prepare_free(row)
        change_machine(self.machines[1].pk, {'status': 'maintenance'})
        path = f"tournaments/{row['id']}/team/batches/preview/"
        self.assertEqual(self.write(path, {'machine_ids': [self.machines[1].pk]}).status_code, 409)
        self.assertEqual(self.write(path, {'machine_ids': [self.machines[0].pk] * 2}).status_code, 400)
        batch = self.batch(row['id'])
        self.assertEqual(personal.fixed_tables.get().reservations.get(status='active').machine_id, self.machines[0].pk)
        self.confirm_batch(row['id'], batch); self.complete(row['id'])
        self.assertTrue(personal.fixed_tables.filter(reservations__status='active').exists())
        self.assertFalse(Tournament.objects.get(pk=row['id']).fixed_tables.filter(reservations__status='active').exists())

    def test_plan_pagination_and_strict_writes_preserve_server_roster(self):
        row = self.create(total=51); self.generate(row['id'])
        first = self.read(f"tournaments/{row['id']}/team/plans/")
        second = self.read(f"tournaments/{row['id']}/team/plans/?page=2")
        self.assertEqual((len(first['results']), first['count'], first['has_next']), (50, 51, True))
        self.assertEqual((len(second['results']), second['results'][0]['match_number'], second['has_next']), (1, 51, False))
        self.assertEqual(self.client.get(f"/api/v1/tournaments/{row['id']}/team/plans/?page=0").status_code, 400)
        p = first['results'][0]
        self.assertEqual(self.write(f"tournaments/{row['id']}/team/plans/{p['id']}/", {'version': p['version'], 'status': 'started'}, 'put').status_code, 400)
        self.assertEqual(self.write(f"tournaments/{row['id']}/", {'revision': Tournament.objects.get(pk=row['id']).revision,
            'champion_team_id': row['teams'][0]['id']}, 'patch').status_code, 400)
        self.assertEqual(TeamMatchPlan.objects.get(pk=p['id']).version, p['version'])

    def test_manual_position_team_swaps_preserve_representatives_and_equal_stage_games(self):
        row = self.create(5, 2, mode='positions', games=4)
        self.expect_data(self.write(f"tournaments/{row['id']}/", {'revision': row['revision'],
            'pairing_strategy': 'team_manual_v1', 'positions': ['先锋']}, 'patch'))
        self.generate(row['id'])
        stage = self.read(f"tournaments/{row['id']}/workspace/")['stages'][0]
        current = self.read(f"tournaments/{row['id']}/")
        self.expect_data(self.write(f"tournaments/{row['id']}/team/stages/{stage['id']}/representatives/", {
            'revision': current['revision'], 'captain_supplied': True,
            'representatives': [{'team_id': t['id'], 'member_id': t['members'][0]['id']} for t in row['teams']]}, 'put'))
        plans = self.plans(row['id'], stage['id']); first, second = plans[:2]
        all_ids = {team['id'] for team in row['teams']}
        missing_first = (all_ids - set(first['team_ids'])).pop()
        missing_second = (all_ids - set(second['team_ids'])).pop()
        new_first = [missing_first if pk == missing_second else pk for pk in first['team_ids']]
        new_second = [missing_second if pk == missing_first else pk for pk in second['team_ids']]
        updated = []
        for plan, ids in ((first, new_first), (second, new_second)):
            updated.append(self.expect_data(self.write(f"tournaments/{row['id']}/team/plans/{plan['id']}/", {
                'version': plan['version'], 'team_ids': ids, 'captain_supplied': False}, 'put')))
        member_by_team = {team['id']: team['members'][0]['id'] for team in row['teams']}
        for plan in updated:
            self.assertEqual(plan['lineup'], {str(pk): member_by_team[pk] for pk in plan['team_ids']})
            self.assertTrue(plan['captain_supplied'])
        plans = self.plans(row['id'], stage['id'])
        self.expect_data(self.write(f"tournaments/{row['id']}/team/plans/confirm/", {'confirmed': True,
            'plan_sources': [{'match_id': p['id'], 'version': p['version']} for p in plans]}))
        self.assertEqual(Counter(pk for p in plans for pk in p['team_ids']), Counter({pk: 4 for pk in all_ids}))
