"""Confirmed-result corrections preserve play history and use exact live scores."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from fractions import Fraction
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from rest_framework.exceptions import ValidationError

from .competition_services import (
    correct_result, finish, generate, mapping, preview, preview_result, ranking,
    record_lottery, confirm_lottery, result_corrections, result_snapshot, source_versions, write_result,
)
from .models import RoundSeat, RoundTable, TournamentRound, TableResult, TableResultCorrection, TournamentMachineReservation
from .scoring import unpack
from .services import TournamentConflict
from .tests_competition import Fixtures


def values(table, points):
    return [{'participant_id': seat.participant_id, 'raw_points': point} for seat, point in zip(table.seats.order_by('id'), points)]


class ResultCorrectionTests(Fixtures, TestCase):
    def setUp(self):
        self.setup_data()

    def assert_conflict(self, code, operation):
        with self.assertRaises(TournamentConflict) as caught:
            operation()
        self.assertEqual(caught.exception.default_code, code)

    def test_correct_round_one_after_round_two_preserves_seats_scores_and_mapping(self):
        tournament = self.tournament(8, 3)
        first = self.first(tournament)
        for table in first.tables.all():
            self.confirm(table)
        second = generate(tournament.pk, self.admin, 2)
        for table in second.tables.all():
            self.confirm(table, [25000] * 4)
        table = first.tables.first()
        original = result_snapshot(TableResult.objects.get(table=table))
        seats = list(RoundSeat.objects.values_list('id', 'round_id', 'table_id', 'participant_id', 'seat_wind'))
        second_results = list(TableResult.objects.filter(table__round=second).values())
        second_snapshot = deepcopy(second.generation_snapshot)
        reservations = list(TournamentMachineReservation.objects.values())
        actor = get_user_model().objects.create_user(username='correction_second_admin', is_staff=True)
        result = correct_result(table.pk, actor, 1, points=values(table, [10000, 20000, 30000, 40000]), reason='原始点数录入顺序有误')
        self.assertEqual((result['status'], result['version'], result['correction_count']), ('confirmed', 2, 1))
        self.assertEqual(list(RoundSeat.objects.values_list('id', 'round_id', 'table_id', 'participant_id', 'seat_wind')), seats)
        self.assertEqual(list(TableResult.objects.filter(table__round=second).values()), second_results)
        second.refresh_from_db()
        self.assertEqual(second.generation_snapshot, second_snapshot)
        self.assertEqual(list(TournamentMachineReservation.objects.values()), reservations)
        audit = TableResultCorrection.objects.get()
        self.assertEqual(audit.before_snapshot, original)
        self.assertEqual(audit.after_snapshot, result_snapshot(TableResult.objects.get(table=table)))
        self.assertEqual((audit.corrected_by_id, audit.reason), (actor.pk, '原始点数录入顺序有误'))
        self.assertNotEqual(audit.before_snapshot['confirmed_by'], audit.after_snapshot['confirmed_by'])
        row = next(row for row in ranking(tournament)[0] if row['participant_id'] == result['scores'][0]['participant_id'])
        self.assertEqual(unpack(row['total']), unpack(result['scores'][0]['score']))
        third = generate(tournament.pk, self.admin, 3)
        self.assertEqual(third.generation_snapshot['source_versions'], source_versions(tournament))
        self.assertIn({'table_id': table.pk, 'version': 2}, third.generation_snapshot['source_versions'])
        self.assertIn({'table_id': table.pk, 'version': 1}, second_snapshot['source_versions'])
        corrected_player = table.seats.order_by('id').first().participant_id
        self.assertLess(second_snapshot['sorted_participants'].index(corrected_player), 2)
        self.assertGreaterEqual(third.generation_snapshot['sorted_participants'].index(corrected_player), 6)

    def test_legacy_unconfirmed_earlier_round_can_be_recorded_after_later_round_exists(self):
        tournament = self.tournament(rounds=2, rules_version=1)
        first = self.legacy_round(tournament, [self.machines[0]])
        later = TournamentRound.objects.create(tournament=tournament, round_number=2, generated_by=self.admin)
        later_table = RoundTable.objects.create(round=later, table_number=1)
        RoundSeat.objects.bulk_create([RoundSeat(round=later, table=later_table, participant=participant, seat_wind=wind) for participant, wind in zip(tournament.participants.all(), ['east', 'south', 'west', 'north'])])
        seats = list(later.seats.values_list('id', 'participant_id', 'seat_wind'))
        table = first.tables.get()
        draft = write_result(table.pk, self.admin, 0, points=values(table, [25000] * 4))
        confirmed = write_result(table.pk, self.admin, draft['version'], confirm=True)
        self.assertEqual((confirmed['status'], confirmed['version']), ('confirmed', 2))
        self.assertEqual(list(later.seats.values_list('id', 'participant_id', 'seat_wind')), seats)

    def test_cas_noop_and_multiple_corrections_preserve_each_original_record(self):
        tournament = self.tournament(rounds=2)
        table = self.first(tournament).tables.get()
        self.confirm(table)
        points = values(table, [35000, 35000, 20000, 10000])
        correct_result(table.pk, self.admin, 1, points=points)
        original_audit = deepcopy(result_corrections(table.pk)['corrections'][0])
        snapshot = result_snapshot(TableResult.objects.get(table=table))
        self.assert_conflict('stale_result', lambda: correct_result(table.pk, self.admin, 1, points=values(table, [25000] * 4)))
        self.assertEqual(correct_result(table.pk, self.admin, 2, points=points)['version'], 2)
        self.assertEqual(TableResultCorrection.objects.count(), 1)
        self.assertEqual(result_snapshot(TableResult.objects.get(table=table)), snapshot)
        correct_result(table.pk, self.admin, 2, points=values(table, [25000] * 4))
        rows = result_corrections(table.pk)['corrections']
        self.assertEqual([(row['from_version'], row['to_version']) for row in rows], [(2, 3), (1, 2)])
        self.assertEqual(rows[1], original_audit)
        self.assertEqual(rows[0]['before'], rows[1]['after'])

    def test_bad_points_or_reason_leave_original_confirmed_result_intact(self):
        tournament = self.tournament()
        table = self.first(tournament).tables.get()
        self.confirm(table)
        original = result_snapshot(TableResult.objects.get(table=table))
        valid = values(table, [25000] * 4)
        bad = [[], valid[:3], values(table, [0] * 4), values(table, [None, 0, 50000, 50000])]
        bad += [[*valid[:3], valid[0]], [{**valid[0], 'participant_id': 999999}, *valid[1:]]]
        bad += [[{**valid[0], 'raw_points': value}, *valid[1:]] for value in [True, 1.0, '25000', 2**53]]
        for points in bad:
            with self.subTest(points=points), self.assertRaises(ValidationError):
                correct_result(table.pk, self.admin, 1, points=points)
        with self.assertRaises(ValidationError):
            correct_result(table.pk, self.admin, 1, points=valid, reason='x' * 501)
        self.assertEqual(result_snapshot(TableResult.objects.get(table=table)), original)
        self.assertFalse(TableResultCorrection.objects.exists())

    def test_audit_failure_rolls_back_scores_version_and_tournament_revision(self):
        tournament = self.tournament()
        table = self.first(tournament).tables.get()
        self.confirm(table)
        tournament.refresh_from_db()
        revision = tournament.revision
        original = result_snapshot(TableResult.objects.get(table=table))
        with patch('tournaments.competition_services.TableResultCorrection.objects.create', side_effect=IntegrityError('injected audit failure')):
            self.assert_conflict('competition_conflict', lambda: correct_result(table.pk, self.admin, 1, points=values(table, [25000] * 4)))
        tournament.refresh_from_db()
        self.assertEqual(tournament.revision, revision)
        self.assertEqual(result_snapshot(TableResult.objects.get(table=table)), original)
        self.assertFalse(TableResultCorrection.objects.exists())

    def test_correction_audit_rejects_duplicate_and_invalid_version_steps(self):
        tournament = self.tournament()
        table = self.first(tournament).tables.get()
        self.confirm(table)
        correct_result(table.pk, self.admin, 1, points=values(table, [25000] * 4))
        audit = TableResultCorrection.objects.get()
        for from_version, to_version in [(1, 2), (0, 1), (2, 4)]:
            with self.subTest(from_version=from_version, to_version=to_version), self.assertRaises(IntegrityError), transaction.atomic():
                TableResultCorrection.objects.create(result=audit.result, from_version=from_version, to_version=to_version, before_snapshot=audit.before_snapshot, after_snapshot=audit.after_snapshot, corrected_by=self.admin)
        self.assertEqual(TableResultCorrection.objects.count(), 1)

    def test_legacy_zero_and_long_decimal_oka_corrections_stay_lossless(self):
        custom = '12.' + '1234567890' * 6 + '1'
        for index, (version, oka) in enumerate([(1, None), (2, '0'), (2, custom)]):
            tournament = self.tournament(rules_version=version, oka_override=oka)
            table = self.first(tournament, [self.machines[index].pk]).tables.get()
            self.confirm(table)
            result = correct_result(table.pk, self.admin, 1, points=values(table, [30000, 30000, 30000, 10000]))
            expected = (30 + (Fraction(20) if oka is None else Fraction(oka))) / 3
            self.assertEqual([unpack(row['bonus']) for row in result['scores'][:3]], [expected] * 3)
            self.assertEqual(result['rules']['rules_version'], version)
            if version == 1:
                self.assertNotIn('oka_override', result['rules'])
            self.assertEqual(TableResultCorrection.objects.get(result__table=table).after_snapshot['scores'], result['scores'])

    def test_obsolete_confirmed_lottery_is_preserved_but_not_used_to_finish(self):
        tournament = self.tournament()
        table = self.first(tournament).tables.get()
        self.confirm(table, [25000] * 4)
        members, draw = self.draw(tournament)
        old = record_lottery(tournament.pk, self.admin, draw)
        confirm_lottery(tournament.pk, old.pk, self.admin)
        old_versions = deepcopy(old.source_versions)
        correct_result(table.pk, self.admin, 1, points=values(table, [40000, 30000, 20000, 10000]))
        self.assertTrue(preview(tournament.pk)['ready'])
        self.assertTrue(all(row['lottery_id'] is None for row in preview(tournament.pk)['standings']))
        correct_result(table.pk, self.admin, 2, points=values(table, [25000] * 4))
        self.assertEqual([set(group) for group in preview(tournament.pk)['unresolved_groups']], [set(members)])
        self.assert_conflict('lottery_required', lambda: finish(tournament.pk, self.admin, source_versions(tournament)))
        current = record_lottery(tournament.pk, self.admin, draw | {'source_versions': source_versions(tournament), 'order': members[::-1]})
        confirm_lottery(tournament.pk, current.pk, self.admin)
        final = finish(tournament.pk, self.admin, source_versions(tournament))
        self.assertEqual(final['lottery_ids'], [current.pk])
        old.refresh_from_db()
        self.assertEqual(old.source_versions, old_versions)
        self.assertIsNotNone(old.confirmed_at)
        self.assertIsNone(old.voided_at)

    def test_expired_pending_lottery_cannot_confirm_or_block_new_current_record(self):
        tournament = self.tournament()
        table = self.first(tournament).tables.get()
        self.confirm(table, [25000] * 4)
        _, draw = self.draw(tournament)
        old = record_lottery(tournament.pk, self.admin, draw)
        correct_result(table.pk, self.admin, 1, points=values(table, [30000, 30000, 30000, 10000]))
        self.assert_conflict('lottery_conflict', lambda: confirm_lottery(tournament.pk, old.pk, self.admin))
        correct_result(table.pk, self.admin, 2, points=values(table, [25000] * 4))
        fresh = record_lottery(tournament.pk, self.admin, draw | {'source_versions': source_versions(tournament)})
        self.assertNotEqual(fresh.pk, old.pk)
        old.refresh_from_db()
        self.assertIsNone(old.confirmed_at)

    def test_completed_tournament_remains_immutable_and_history_is_readable(self):
        tournament = self.tournament()
        table = self.first(tournament).tables.get()
        self.confirm(table)
        correct_result(table.pk, self.admin, 1, points=values(table, [35000, 35000, 20000, 10000]))
        self.resolve(tournament)
        final = finish(tournament.pk, self.admin, source_versions(tournament))
        original = result_snapshot(TableResult.objects.get(table=table))
        self.assert_conflict('tournament_not_started', lambda: correct_result(table.pk, self.admin, 2, points=values(table, [25000] * 4)))
        self.assert_conflict('tournament_not_started', lambda: preview_result(table.pk, 2, values(table, [25000] * 4)))
        self.assertEqual(result_snapshot(TableResult.objects.get(table=table)), original)
        tournament.refresh_from_db()
        self.assertEqual(tournament.final_snapshot, final)
        self.assertEqual(len(result_corrections(table.pk)['corrections']), 1)

    def test_preview_is_readonly_partial_imbalanced_and_handles_safe_point_limits(self):
        tournament = self.tournament(rounds=2)
        table = self.first(tournament).tables.get()
        self.confirm(table)
        generate(tournament.pk, self.admin, 2)
        original = result_snapshot(TableResult.objects.get(table=table))
        tournament.refresh_from_db()
        revision = tournament.revision
        partial = preview_result(table.pk, 1, values(table, [-1000, None, 0, None]))
        self.assertFalse(partial['complete'])
        by_id = {row['participant_id']: row for row in partial['scores']}
        for value in values(table, [-1000, None, 0, None]):
            row = by_id[value['participant_id']]
            self.assertIsNone(row['score'])
            self.assertEqual(unpack(row['base']) if row['base'] else None, None if value['raw_points'] is None else Fraction(value['raw_points'] - 30000, 1000))
        imbalanced = preview_result(table.pk, 1, values(table, [30000, 30000, 30000, 20000]))
        self.assertTrue(imbalanced['complete'])
        self.assertFalse(imbalanced['valid_total'])
        self.assertEqual(imbalanced['difference'], '10000')
        largest = preview_result(table.pk, 1, values(table, [2**53 - 1] * 4))
        self.assertEqual(largest['total'], str(4 * (2**53 - 1)))
        self.assertEqual(result_snapshot(TableResult.objects.get(table=table)), original)
        self.assertFalse(TableResultCorrection.objects.exists())
        tournament.refresh_from_db()
        self.assertEqual(tournament.revision, revision)

    def test_standings_and_finish_token_use_the_same_result_batch_during_correction(self):
        tournament = self.tournament()
        table = self.first(tournament).tables.get()
        self.confirm(table)
        old_champion = table.seats.order_by('id').first().participant_id
        original_ranking = ranking

        def correct_after_ranking(*args, **kwargs):
            output = original_ranking(*args, **kwargs)
            correct_result(table.pk, self.admin, 1, points=values(table, [10000, 20000, 30000, 40000]))
            return output

        with patch('tournaments.competition_services.ranking', side_effect=correct_after_ranking):
            displayed = preview(tournament.pk)
        self.assertEqual(displayed['standings'][0]['participant_id'], old_champion)
        self.assertEqual(displayed['source_versions'], [{'table_id': table.pk, 'version': 1}])
        self.assertEqual(source_versions(tournament), [{'table_id': table.pk, 'version': 2}])
        self.assert_conflict('stale_standings', lambda: finish(tournament.pk, self.admin, displayed['source_versions']))
        tournament.refresh_from_db()
        self.assertEqual(tournament.status, 'started')
        self.assertFalse(tournament.final_snapshot)

    def test_confirmation_after_batch_read_does_not_mark_old_preview_as_complete(self):
        tournament = self.tournament()
        table = self.first(tournament).tables.get()
        original_ranking = ranking

        def confirm_after_ranking(*args, **kwargs):
            output = original_ranking(*args, **kwargs)
            self.confirm(table)
            return output

        with patch('tournaments.competition_services.ranking', side_effect=confirm_after_ranking):
            displayed = preview(tournament.pk)
        self.assertFalse(displayed['all_results_confirmed'])
        self.assertFalse(displayed['ready'])
        self.assertEqual(displayed['source_versions'], [])
        self.assertTrue(all(row['confirmed_rounds'] == 0 for row in displayed['standings']))
        self.assert_conflict('stale_standings', lambda: finish(tournament.pk, self.admin, displayed['source_versions']))


class ResultCorrectionApiTests(Fixtures, TestCase):
    def setUp(self):
        self.setup_data()
        self.tournament_ = self.tournament(8, 2)
        first = self.first(self.tournament_)
        for table in first.tables.all():
            self.confirm(table)
        self.table = first.tables.first()
        generate(self.tournament_.pk, self.admin, 2)
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.admin)
        self.token = self.client.get('/api/v1/auth/csrf/').json()['data']['csrf_token']

    def post(self, endpoint, body, client=None, token=None):
        return (client or self.client).post(f'/api/v1/round-tables/{self.table.pk}/result/{endpoint}/', body, content_type='application/json', HTTP_X_CSRFTOKEN=token or self.token)

    def test_correction_after_second_round_and_readonly_history_contract(self):
        original = deepcopy(TableResult.objects.get(table=self.table).points)
        response = self.post('correct', {'version': 1, 'points': values(self.table, [35000, 35000, 20000, 10000]), 'reason': '抄录修正'})
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()['data']
        self.assertEqual((data['version'], data['status'], data['correction_count']), (2, 'confirmed', 1))
        url = f'/api/v1/round-tables/{self.table.pk}/result/corrections/'
        history = self.client.get(url)
        self.assertEqual(history.status_code, 200)
        record = history.json()['data']['corrections'][0]
        self.assertEqual((record['before']['points'], record['after']['points']), (original, data['points']))
        self.assertEqual((record['corrected_by'], record['reason']), (self.admin.pk, '抄录修正'))
        self.assertEqual(record['corrected_by_username'], self.admin.username)
        self.assertEqual(self.client.delete(url, HTTP_X_CSRFTOKEN=self.token).status_code, 405)
        stale = self.post('correct', {'version': 1, 'points': values(self.table, [25000] * 4)})
        self.assertEqual((stale.status_code, stale.json()['error']['code']), (409, 'stale_result'))
        self.assertEqual(self.post('preview', {'version': 1, 'points': values(self.table, [25000] * 4)}).status_code, 409)

    def test_preview_fraction_response_does_not_write(self):
        row = TableResult.objects.get(table=self.table)
        before = result_snapshot(row)
        response = self.post('preview', {'version': 1, 'points': values(self.table, [30000, 30000, 30000, 10000])})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['scores'][0]['score'], {'numerator': '50', 'denominator': '3'})
        row.refresh_from_db()
        self.assertEqual(result_snapshot(row), before)
        self.assertFalse(TableResultCorrection.objects.exists())

    def test_strict_inputs_reject_unknown_fields_and_noninteger_numbers(self):
        original = result_snapshot(TableResult.objects.get(table=self.table))
        for endpoint in ['correct', 'preview']:
            base = {'version': 1, 'points': values(self.table, [25000] * 4)}
            for body in [base | {'scores': []}, base | {'version': True}, base | {'version': '1'}, base | {'version': 1.0}, base | {'points': []}, base | {'points': values(self.table, [0.0, 0, 50000, 50000])}]:
                # Empty input is a valid incomplete preview, but never a correction.
                if endpoint == 'preview' and body.get('points') == [] and set(body) == {'version', 'points'}:
                    continue
                self.assertEqual(self.post(endpoint, body).status_code, 400, body)
        self.assertEqual(result_snapshot(TableResult.objects.get(table=self.table)), original)

    def test_admin_session_and_csrf_protect_preview_correction_and_history(self):
        body = {'version': 1, 'points': values(self.table, [25000] * 4)}
        for endpoint in ['correct', 'preview']:
            url = f'/api/v1/round-tables/{self.table.pk}/result/{endpoint}/'
            self.assertEqual(self.client.post(url, body, content_type='application/json').status_code, 403)
            self.assertEqual(self.post(endpoint, body, token='invalid').status_code, 403)
        for user in [None, self.users[0]]:
            client = Client(enforce_csrf_checks=True)
            if user:
                client.force_login(user)
            token = client.get('/api/v1/auth/csrf/').json()['data']['csrf_token']
            for endpoint in ['correct', 'preview']:
                self.assertEqual(self.post(endpoint, body, client=client, token=token).status_code, 403)
            self.assertEqual(client.get(f'/api/v1/round-tables/{self.table.pk}/result/corrections/').status_code, 403)
        self.assertEqual(TableResult.objects.get(table=self.table).version, 1)
        self.assertFalse(TableResultCorrection.objects.exists())

    def test_workspace_get_keeps_displayed_standings_and_finish_token_together(self):
        tournament = self.tournament()
        table = self.first(tournament, [self.machines[2].pk]).tables.get()
        self.confirm(table)
        original = ranking(tournament)[0]
        original_versions = source_versions(tournament)
        original_ranking = ranking

        def correct_after_ranking(*args, **kwargs):
            output = original_ranking(*args, **kwargs)
            correct_result(table.pk, self.admin, 1, points=values(table, [10000, 20000, 30000, 40000]))
            return output

        with patch('tournaments.competition_services.ranking', side_effect=correct_after_ranking):
            response = self.client.get(f'/api/v1/tournaments/{tournament.pk}/workspace/')
        self.assertEqual(response.status_code, 200)
        displayed = response.json()['data']
        self.assertEqual(displayed['standings'], original)
        self.assertEqual(displayed['source_versions'], original_versions)
        finish_response = self.client.post(f'/api/v1/tournaments/{tournament.pk}/complete/', {'source_versions': displayed['source_versions'], 'confirmed': True}, content_type='application/json', HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual((finish_response.status_code, finish_response.json()['error']['code']), (409, 'stale_standings'))
        tournament.refresh_from_db()
        self.assertEqual(tournament.status, 'started')
        self.assertFalse(tournament.final_snapshot)


class ConcurrentResultCorrectionTests(Fixtures, TransactionTestCase):
    def setUp(self):
        self.setup_data()

    def race(self, operations):
        barrier = Barrier(len(operations))
        def worker(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                operation()
                return 'ok'
            except TournamentConflict as error:
                return error.default_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(operations)) as executor:
            return list(executor.map(worker, operations))

    def test_same_version_parallel_corrections_only_one_commits(self):
        tournament = self.tournament()
        table = self.first(tournament).tables.get()
        self.confirm(table)
        results = self.race([lambda: correct_result(table.pk, self.admin, 1, points=values(table, [35000, 35000, 20000, 10000])), lambda: correct_result(table.pk, self.admin, 1, points=values(table, [25000] * 4))])
        self.assertEqual(results.count('ok'), 1, results)
        self.assertTrue(set(results) <= {'ok', 'stale_result', 'tournament_busy'})
        self.assertEqual(TableResult.objects.get(table=table).version, 2)
        self.assertEqual(TableResultCorrection.objects.count(), 1)

    def test_finish_race_never_changes_completed_snapshot(self):
        tournament = self.tournament()
        table = self.first(tournament).tables.get()
        self.confirm(table)
        versions = source_versions(tournament)
        results = self.race([lambda: correct_result(table.pk, self.admin, 1, points=values(table, [10000, 20000, 30000, 40000])), lambda: finish(tournament.pk, self.admin, versions)])
        self.assertTrue(set(results) <= {'ok', 'stale_standings', 'tournament_not_started', 'tournament_busy'}, results)
        tournament.refresh_from_db()
        if tournament.status == 'started':
            finish(tournament.pk, self.admin, source_versions(tournament))
        tournament.refresh_from_db()
        expected = ranking(tournament)[0]
        self.assertEqual(tournament.final_snapshot['standings'], expected)
        self.assertEqual(tournament.final_snapshot['source_versions'], source_versions(tournament))
