from copy import deepcopy
from fractions import Fraction
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from machines.services import change_machine
from . import competition_services as svc
from .models import EliminationRecord, LotteryRecord, RoundSeat, RoundTable, TableResult, Tournament, TournamentRound, TournamentMachineReservation as Reservation
from .pairing import MANUAL, RANDOM, RANKED, SWISS_REPEATS, SWISS_SCORES
from .pairing_plan import preview as pairing_preview
from .round_services import validate_round_structure
from .scoring import unpack
from .services import create_tournament, mutate_tournament, TournamentConflict
from .tests_competition import Fixtures
from . import tests_competition as competition_fixtures


class EventFixtures(Fixtures):
    def confirm_unique(self, round_):
        for table in round_.tables.all():
            adjustment = round_.round_number * 101 + table.table_number * 13
            self.confirm(table, [40000 + adjustment, 30000 + 2 * adjustment, 20000 - adjustment, 10000 - 2 * adjustment])

    def eliminate(self, tournament, plan=None):
        plan = plan or svc.elimination_preview(tournament)
        return svc.confirm_elimination(tournament.pk, self.admin, round_number=plan['round_number'],
            source_versions=plan['source_versions'], participant_statuses=plan['participant_statuses'],
            participant_ids=[row['participant_id'] for row in plan['candidates']])

    def resolve_final(self, tournament):
        current = svc.preview(tournament.pk)
        for group in current['unresolved_groups']:
            row = svc.record_lottery(tournament.pk, self.admin, {'members': group, 'order': group[::-1],
                'source_versions': current['source_versions'], 'participant_statuses': current['participant_statuses'],
                'method': '现场纸签', 'description': '管理员和选手公开见证', 'drawn_at': timezone.now()})
            svc.confirm_lottery(tournament.pk, row.pk, self.admin)

    def assert_conflict(self, code, operation):
        with self.assertRaises(TournamentConflict) as error:
            operation()
        self.assertEqual(error.exception.default_code, code)


class EventFlowTests(EventFixtures, TestCase):
    def setUp(self):
        self.setup_data()

    def test_sixteen_six_rounds_optional_elimination_keeps_four_until_end(self):
        tournament = self.tournament(16, 6, pairing_strategy=RANKED, ranked_table_bonuses=['5', '2', '1', '0'])
        original_ids = set(tournament.participants.values_list('pk', flat=True))
        expected_sizes = [16, 16, 12, 12, 8, 4]
        prior_seats = []
        for number, size in enumerate(expected_sizes, 1):
            round_ = self.first(tournament) if number == 1 else svc.generate(tournament.pk, self.admin, number)
            self.assertEqual(round_.seats.count(), size)
            self.assertEqual(round_.tables.count(), size // 4)
            self.assertEqual(list(round_.tables.values_list('table_number', flat=True)), list(range(1, size // 4 + 1)))
            validate_round_structure(round_)
            self.confirm_unique(round_)
            current = list(RoundSeat.objects.filter(round__tournament=tournament).order_by('id').values_list('id', 'participant_id', 'table_id', 'seat_wind'))
            self.assertEqual(current[:len(prior_seats)], prior_seats)
            prior_seats = current
            if number in (2, 4, 5):
                plan = svc.elimination_preview(tournament)
                self.assertTrue(plan['ready'])
                self.eliminate(tournament, plan)
                self.assert_conflict('elimination_already_confirmed', lambda: self.eliminate(tournament, plan))
            elif number == 6:
                self.assertIsNone(svc.elimination_preview(tournament))
        self.resolve_final(tournament)
        snapshot = svc.finish(tournament.pk, self.admin, svc.source_versions(tournament), svc.participant_statuses(tournament))
        self.assertEqual(len(snapshot['standings']), 16)
        self.assertEqual({row['rank'] for row in snapshot['standings']}, set(range(1, 17)))
        self.assertEqual([record['round_number'] for record in snapshot['eliminations']], [2, 4, 5])
        self.assertTrue(all(row['eliminated_after_round'] is None for row in snapshot['standings'][:4]))
        self.assertEqual(set(tournament.participants.values_list('pk', flat=True)), original_ids)
        self.assertTrue(all(user.is_active for user in self.users))
        self.assertEqual(tournament.fixed_tables.count(), 4)
        self.assertFalse(Reservation.objects.filter(table__tournament=tournament, status='active').exists())

    def test_four_remaining_continue_all_configured_rounds(self):
        tournament = self.tournament(8, 4)
        self.confirm_unique(self.first(tournament))
        self.eliminate(tournament)
        for number in (2, 3, 4):
            round_ = svc.generate(tournament.pk, self.admin, number)
            self.assertEqual(round_.seats.count(), 4)
            self.confirm_unique(round_)
            self.assertIsNone(svc.elimination_preview(tournament))
        self.assertEqual(tournament.rounds.count(), 4)
        self.assertEqual(EliminationRecord.objects.count(), 1)

    def test_boundary_tie_requires_public_draw_then_separate_elimination_confirmation(self):
        tournament = self.tournament(8, 2)
        for table in self.first(tournament).tables.all(): self.confirm(table, [25000] * 4)
        plan = svc.elimination_preview(tournament)
        self.assertFalse(plan['ready'])
        self.assertEqual(plan['candidates'], [])
        group = plan['unresolved_groups'][0]
        self.assertEqual(len(group), 8)
        self.assert_conflict('elimination_lottery_required', lambda: svc.confirm_elimination(tournament.pk, self.admin,
            round_number=1, source_versions=plan['source_versions'], participant_statuses=plan['participant_statuses'], participant_ids=group[-4:]))
        values = {'purpose': 'elimination', 'round_number': 1, 'members': group, 'order': group[::-1],
                  'source_versions': plan['source_versions'], 'participant_statuses': plan['participant_statuses'],
                  'method': '公开纸签', 'description': '全员依次抽取，靠前者晋级', 'drawn_at': timezone.now()}
        draw = svc.record_lottery(tournament.pk, self.admin, values)
        self.assert_conflict('lottery_pending', lambda: svc.record_lottery(tournament.pk, self.admin, values))
        self.assertFalse(tournament.participants.filter(eliminated_after_round__isnull=False).exists())
        svc.confirm_lottery(tournament.pk, draw.pk, self.admin)
        current = svc.elimination_preview(tournament)
        self.assertTrue(current['ready'])
        self.assertEqual([row['participant_id'] for row in current['candidates']], group[::-1][-4:])
        self.assertEqual(EliminationRecord.objects.count(), 0)
        self.eliminate(tournament, current)
        record = EliminationRecord.objects.get()
        self.assertEqual(record.lottery_ids, [draw.pk])
        self.assertEqual(record.confirmed_by, self.admin)
        self.assertEqual(len(record.standings_snapshot), 8)
        self.assert_conflict('lottery_conflict', lambda: svc.void_lottery(tournament.pk, draw.pk, self.admin, '不可作废已确认记录'))
        second = svc.generate(tournament.pk, self.admin, 2)
        self.confirm_unique(second)
        self.assertTrue(all(row['lottery_id'] != draw.pk for row in svc.ranking(tournament)[0]))

    def test_ties_wholly_inside_eliminated_group_do_not_need_boundary_draw(self):
        tournament = self.tournament(8, 2)
        for table in self.first(tournament).tables.all(): self.confirm(table)
        plan = svc.elimination_preview(tournament)
        self.assertTrue(plan['ready'])
        self.assertEqual(plan['unresolved_groups'], [])
        self.assertEqual(len(plan['candidates']), 4)
        self.eliminate(tournament, plan)
        self.assertEqual(LotteryRecord.objects.count(), 0)

    def test_corrected_old_score_preserves_elimination_and_existing_rounds(self):
        tournament = self.tournament(8, 3)
        first = self.first(tournament)
        self.confirm_unique(first)
        self.eliminate(tournament)
        eliminated = list(tournament.participants.filter(eliminated_after_round=1).values_list('pk', flat=True))
        record_before = deepcopy(EliminationRecord.objects.get().standings_snapshot)
        second = svc.generate(tournament.pk, self.admin, 2)
        before = deepcopy(second.generation_snapshot)
        self.confirm_unique(second)
        table = first.tables.filter(seats__participant_id=eliminated[0]).get()
        others = [seat.participant_id for seat in table.seats.all() if seat.participant_id != eliminated[0]]
        points = [{'participant_id': eliminated[0], 'raw_points': 900000}] + [
            {'participant_id': pk, 'raw_points': value} for pk, value in zip(others, [30000, 20000, -850000])]
        svc.correct_result(table.pk, self.admin, 1, points=points)
        second.refresh_from_db()
        self.assertEqual(second.generation_snapshot, before)
        self.assertEqual(EliminationRecord.objects.get().standings_snapshot, record_before)
        third = svc.generate(tournament.pk, self.admin, 3)
        self.assertFalse(third.seats.filter(participant_id__in=eliminated).exists())
        self.confirm_unique(third)
        self.resolve_final(tournament)
        result = svc.finish(tournament.pk, self.admin, svc.source_versions(tournament), svc.participant_statuses(tournament))
        corrected = next(row for row in result['standings'] if row['participant_id'] == eliminated[0])
        self.assertGreater(unpack(corrected['total']), unpack(result['standings'][0]['total']))
        self.assertGreater(corrected['rank'], 4)
        self.assertNotIn(result['champion_id'], eliminated)

    def test_pairing_token_excludes_eliminated_players_and_keeps_original_random_order(self):
        for strategy in (MANUAL, RANDOM, RANKED):
            tournament = self.tournament(8, 2, pairing_strategy=strategy)
            first_plan = pairing_preview(tournament.pk, self.admin, 1)
            first = svc.generate(tournament.pk, self.admin, 1, machine_ids=[m.pk for m in self.machines[:2]],
                                 pairing_token=first_plan['token'], participant_groups=[table['participant_ids'] for table in first_plan['tables']] if strategy == MANUAL else None)
            self.confirm_unique(first)
            tournament.refresh_from_db()
            original_order = tournament.first_round_order[:]
            stale = pairing_preview(tournament.pk, self.admin, 2)
            self.eliminate(tournament)
            self.assert_conflict('stale_pairing', lambda: svc.generate(tournament.pk, self.admin, 2,
                pairing_token=stale['token'], participant_groups=[table['participant_ids'] for table in stale['tables']] if strategy == MANUAL else None))
            current = pairing_preview(tournament.pk, self.admin, 2)
            self.assertEqual(len(current['participants']), 4)
            groups = [table['participant_ids'] for table in current['tables']]
            second = svc.generate(tournament.pk, self.admin, 2, pairing_token=current['token'], participant_groups=groups if strategy == MANUAL else None)
            self.assertEqual(second.seats.count(), 4)
            tournament.refresh_from_db()
            self.assertEqual(tournament.first_round_order, original_order)
            self.assertEqual(len(second.generation_snapshot['first_round_order']), 8)

    def test_elimination_rolls_back_record_and_all_four_statuses_on_failure(self):
        tournament = self.tournament(8, 2)
        self.confirm_unique(self.first(tournament))
        plan = svc.elimination_preview(tournament)
        with patch('tournaments.competition_services.EliminationRecord.objects.create', side_effect=IntegrityError('injected')):
            self.assert_conflict('competition_conflict', lambda: self.eliminate(tournament, plan))
        self.assertEqual(EliminationRecord.objects.count(), 0)
        self.assertFalse(tournament.participants.filter(eliminated_after_round__isnull=False).exists())
        with patch('tournaments.competition_services.release_reservation', side_effect=IntegrityError('injected after qualification update')):
            self.assert_conflict('competition_conflict', lambda: self.eliminate(tournament, plan))
        self.assertEqual(EliminationRecord.objects.count(), 0)
        self.assertFalse(tournament.participants.filter(eliminated_after_round__isnull=False).exists())
        self.assertEqual(Reservation.objects.filter(table__tournament=tournament, status='active').count(), 2)
        self.eliminate(tournament, plan)
        with self.assertRaises(IntegrityError), transaction.atomic():
            EliminationRecord.objects.create(round=tournament.rounds.get(), participant_ids=[], source_versions=[],
                participant_statuses=[], standings_snapshot=[], confirmed_by=self.admin)
        with self.assertRaises(IntegrityError), transaction.atomic():
            tournament.participants.update(eliminated_after_round=6)

    def test_partial_round_and_final_round_cannot_eliminate(self):
        tournament = self.tournament(8, 2)
        first = self.first(tournament)
        self.confirm(first.tables.first())
        self.assertIsNone(svc.elimination_preview(tournament))
        self.assert_conflict('results_incomplete', lambda: svc.elimination_preview(tournament, required=True))
        self.confirm(first.tables.last())
        second = svc.generate(tournament.pk, self.admin, 2)
        self.confirm_unique(second)
        self.assert_conflict('elimination_not_available', lambda: svc.elimination_preview(tournament, required=True))

    def test_empty_qualification_source_is_rejected_and_audit_uses_complete_server_snapshot(self):
        tournament = self.tournament(8, 2)
        self.confirm_unique(self.first(tournament))
        plan = svc.elimination_preview(tournament)
        for invalid in ([], None):
            with self.assertRaises(ValidationError):
                svc.confirm_elimination(tournament.pk, self.admin, round_number=1, source_versions=plan['source_versions'],
                    participant_statuses=invalid, participant_ids=[row['participant_id'] for row in plan['candidates']])
            self.assertEqual(EliminationRecord.objects.count(), 0)
            self.assertFalse(tournament.participants.filter(eliminated_after_round__isnull=False).exists())
            self.assertEqual(Reservation.objects.filter(table__tournament=tournament, status='active').count(), 2)
        self.eliminate(tournament, plan)
        record = EliminationRecord.objects.get()
        self.assertEqual(record.participant_statuses, plan['participant_statuses'])
        self.assertEqual(len(record.participant_statuses), 8)
        self.assertEqual(record.source_versions, plan['source_versions'])

    def test_legacy_missing_earlier_scores_blocks_elimination_on_incomplete_cumulative_ranking(self):
        tournament = self.tournament(8, 3)
        first = self.first(tournament)
        # Legacy rounds can predate score entry. Preserve that history, but do
        # not eliminate anybody until the complete cumulative basis is known.
        second = TournamentRound.objects.create(tournament=tournament, round_number=2, generated_by=self.admin)
        for original in first.tables.all():
            table = RoundTable.objects.create(round=second, table_number=original.table_number, tournament_table=original.tournament_table,
                                              machine_snapshot=original.machine_snapshot, bonus_source='ranked_event_config_v1')
            RoundSeat.objects.bulk_create([RoundSeat(round=second, table=table, participant=seat.participant, seat_wind=seat.seat_wind)
                                          for seat in original.seats.all()])
        self.confirm_unique(second)
        self.assertIsNone(svc.elimination_preview(tournament))
        self.assert_conflict('results_incomplete', lambda: svc.elimination_preview(tournament, required=True))
        self.assertEqual(EliminationRecord.objects.count(), 0)
        self.confirm_unique(first)
        self.assertIsNotNone(svc.elimination_preview(tournament))

    def test_statistics_only_confirmed_scores_exact_rates_and_all_joint_leaders(self):
        tournament = self.tournament(4, 2)
        table = self.first(tournament).tables.get()
        self.confirm(table, [30000, 30000, 30000, 10000])
        current = svc.preview(tournament.pk)
        leaders = [item['participant_id'] for item in TableResult.objects.get(table=table).scores if item['rank'] == 1]
        self.assertEqual(set(current['statistics']['highest_raw_points']['participant_ids']), set(leaders))
        self.assertEqual(current['statistics']['highest_raw_points']['value'], 30000)
        self.assertEqual(set(current['statistics']['most_firsts']['participant_ids']), set(leaders))
        self.assertEqual(current['statistics']['most_firsts']['value'], 1)
        self.assertEqual(set(current['statistics']['fourth_avoidance']['participant_ids']), set(leaders))
        second = svc.generate(tournament.pk, self.admin, 2).tables.get()
        svc.write_result(second.pk, self.admin, 0, points=[{'participant_id': second.seats.first().participant_id, 'raw_points': 999999}])
        self.assertEqual(svc.preview(tournament.pk)['statistics'], current['statistics'])
        empty = svc.preview(self.tournament().pk)
        self.assertIsNone(empty['statistics']['fourth_avoidance']['value'])
        self.assertIsNone(empty['statistics']['highest_raw_points']['value'])

    def test_fourth_avoidance_rate_is_lossless_two_thirds(self):
        tournament = self.tournament(4, 3)
        target = tournament.participants.first().pk
        for number in (1, 2, 3):
            table = (self.first(tournament) if number == 1 else svc.generate(tournament.pk, self.admin, number)).tables.get()
            ids = list(table.seats.values_list('participant_id', flat=True))
            order = [pk for pk in ids if pk != target]
            order.insert(3 if number == 1 else 0, target)
            svc.write_result(table.pk, self.admin, 0, points=[{'participant_id': pk, 'raw_points': value}
                for pk, value in zip(order, [40000, 30000, 20000, 10000])], confirm=True)
        row = next(row for row in svc.preview(tournament.pk)['standings'] if row['participant_id'] == target)
        self.assertEqual(unpack(row['fourth_avoidance_rate']), Fraction(2, 3))
        self.assertEqual(row['fourth_count'], 1)

    def test_completed_legacy_snapshot_statistics_do_not_rewrite_original(self):
        tournament = self.tournament()
        self.confirm(self.first(tournament).tables.get())
        snapshot = svc.finish(tournament.pk, self.admin, svc.source_versions(tournament))
        legacy = deepcopy(snapshot)
        legacy.pop('statistics')
        legacy.pop('participant_statuses')
        legacy.pop('eliminations')
        for row in legacy['standings']:
            for key in ('highest_raw_points', 'fourth_count', 'fourth_avoidance_rate', 'eliminated_after_round'):
                row.pop(key)
        Tournament.objects.filter(pk=tournament.pk).update(final_snapshot=legacy)
        displayed = svc.preview(tournament.pk)
        self.assertEqual(displayed['statistics']['highest_raw_points']['value'], 40000)
        self.assertEqual([row['total'] for row in displayed['standings']], [row['total'] for row in legacy['standings']])
        tournament.refresh_from_db()
        self.assertEqual(tournament.final_snapshot, legacy)

    def test_shared_machine_finish_only_ends_own_association(self):
        monthly, daily = self.tournament(rounds=2), self.tournament()
        first = self.first(monthly)
        self.confirm(self.first(daily).tables.get())
        client = Client(); client.force_login(self.admin)
        machine = next(row for row in client.get('/api/v1/machine-resources/').json()['data']['results'] if row['machine_id'] == self.machines[0].pk)
        self.assertTrue(machine['assignable'])
        self.assertEqual({row['tournament_id'] for row in machine['reservations']}, {monthly.pk, daily.pk})
        svc.finish(daily.pk, self.admin, svc.source_versions(daily))
        self.assertTrue(Reservation.objects.filter(table__tournament=monthly, status='active').exists())
        self.confirm(first.tables.get())
        self.assertEqual(svc.generate(monthly.pk, self.admin, 2).tables.get().machine_snapshot['machine_id'], self.machines[0].pk)

    def test_minimal_legacy_final_snapshot_has_no_invented_statistics(self):
        tournament = self.tournament()
        self.confirm(self.first(tournament).tables.get())
        result = svc.finish(tournament.pk, self.admin, svc.source_versions(tournament))
        minimal = {**result, 'standings': [{key: row[key] for key in ('participant_id', 'rank', 'total')} for row in result['standings']]}
        minimal.pop('statistics')
        Tournament.objects.filter(pk=tournament.pk).update(final_snapshot=minimal)
        displayed = svc.preview(tournament.pk)
        self.assertIsNone(displayed['statistics']['fourth_avoidance']['value'])
        self.assertIsNone(displayed['statistics']['highest_raw_points']['value'])
        self.assertEqual(displayed['standings'][0]['display_name'], tournament.participants.get(pk=displayed['standings'][0]['participant_id']).display_name_snapshot)
        tournament.refresh_from_db()
        self.assertEqual(tournament.final_snapshot, minimal)

    def test_same_event_duplicate_machine_rejected_and_maintenance_checked_next_round(self):
        tournament = self.tournament(8, 2)
        with self.assertRaises(ValidationError): self.first(tournament, [self.machines[0].pk] * 2)
        first = self.first(tournament)
        self.confirm_unique(first)
        self.assert_conflict('machine_occupied', lambda: svc.replace_machine(tournament.pk, 1, self.admin, self.machines[1].pk, '不得重复'))
        change_machine(self.machines[0].pk, {'status': 'maintenance'})
        self.assert_conflict('machine_unavailable', lambda: svc.generate(tournament.pk, self.admin, 2))
        svc.replace_machine(tournament.pk, 1, self.admin, self.machines[4].pk, '维护时替换')
        self.assertEqual(svc.generate(tournament.pk, self.admin, 2).tables.count(), 2)

    def test_unused_tables_after_elimination_do_not_block_remaining_four(self):
        tournament = self.tournament(8, 2)
        self.confirm_unique(self.first(tournament))
        self.eliminate(tournament)
        change_machine(self.machines[1].pk, {'status': 'disabled'})
        self.assertEqual(svc.generate(tournament.pk, self.admin, 2).tables.count(), 1)

    def test_unused_machine_can_replace_a_faulty_remaining_table_without_an_extra_device(self):
        tournament = self.tournament(8, 2)
        first = self.first(tournament)
        before = [row.machine_snapshot for row in first.tables.all()]
        self.confirm_unique(first)
        self.eliminate(tournament)
        inactive = Reservation.objects.get(table__tournament=tournament, table__ordinal=2)
        self.assertEqual(inactive.status, 'released')
        self.assertIn('淘汰后', inactive.release_reason)
        change_machine(self.machines[0].pk, {'status': 'maintenance'})
        svc.replace_machine(tournament.pk, 1, self.admin, self.machines[1].pk, '复用淘汰后的空桌')
        second = svc.generate(tournament.pk, self.admin, 2)
        self.assertEqual(second.tables.get().machine_snapshot['machine_id'], self.machines[1].pk)
        self.assertEqual([row.machine_snapshot for row in first.tables.all()], before)
        self.assertEqual(tournament.fixed_tables.count(), 2)

    def test_score_correction_during_workspace_read_keeps_elimination_preview_source_together(self):
        tournament = self.tournament(8, 2)
        first = self.first(tournament)
        self.confirm_unique(first)
        original = svc.confirmed_result_rows
        old_plan = svc.elimination_preview(tournament)
        table = first.tables.first()
        def change_after_read(t):
            batch = original(t)
            svc.correct_result(table.pk, self.admin, 1, points=[{'participant_id': seat.participant_id, 'raw_points': value}
                for seat, value in zip(table.seats.all(), [40000, 30000, 20000, 10000])])
            return batch
        with patch('tournaments.competition_services.confirmed_result_rows', side_effect=change_after_read):
            displayed = svc.preview(tournament.pk)
        self.assertEqual(displayed['elimination']['source_versions'], old_plan['source_versions'])
        self.assertEqual(displayed['source_versions'], displayed['elimination']['source_versions'])
        self.assert_conflict('stale_standings', lambda: self.eliminate(tournament, displayed['elimination']))

    def test_elimination_during_read_keeps_standings_and_eligibility_from_same_batch(self):
        tournament = self.tournament(8, 2)
        self.confirm_unique(self.first(tournament))
        original = svc.ranking
        fired = False
        def change_after_participants(*args, **kwargs):
            nonlocal fired
            if not fired and not kwargs.get('active_only'):
                fired = True
                self.eliminate(tournament)
            return original(*args, **kwargs)
        with patch('tournaments.competition_services.ranking', side_effect=change_after_participants):
            displayed = svc.preview(tournament.pk)
        self.assertTrue(all(row['eliminated_after_round'] is None for row in displayed['standings']))
        self.assertTrue(all(row['eliminated_after_round'] is None for row in displayed['participant_statuses']))
        self.assertEqual(displayed['eliminations'], [])
        self.assert_conflict('stale_standings', lambda: svc.check_standings_source(tournament, displayed['source_versions'], displayed['participant_statuses']))
        second = svc.generate(tournament.pk, self.admin, 2)
        self.confirm_unique(second)
        self.resolve_final(tournament)
        self.assert_conflict('stale_standings', lambda: svc.finish(tournament.pk, self.admin, svc.source_versions(tournament), displayed['participant_statuses']))
        self.assert_conflict('stale_standings', lambda: svc.finish(tournament.pk, self.admin, svc.source_versions(tournament)))

    def test_new_swiss_creation_and_switching_rejected_but_existing_drafts_can_keep_strategy(self):
        for strategy in (SWISS_REPEATS, SWISS_SCORES):
            with self.assertRaises(ValidationError): self.tournament(pairing_strategy=strategy)
            draft = create_tournament(self.admin, {'name': '新赛事', 'round_count': 2})
            with self.assertRaises(ValidationError): mutate_tournament(draft.pk, values={'pairing_strategy': strategy})
            Tournament.objects.filter(pk=draft.pk).update(pairing_strategy=strategy)
            kept = mutate_tournament(draft.pk, values={'name': '既有瑞士赛事修改名称', 'pairing_strategy': strategy})
            self.assertEqual(kept.pairing_strategy, strategy)


class EliminationApiTests(EventFixtures, TestCase):
    def setUp(self):
        self.setup_data()
        self.t = self.tournament(8, 2)
        self.confirm_unique(self.first(self.t))
        self.plan = svc.elimination_preview(self.t)
        self.url = f'/api/v1/tournaments/{self.t.pk}/eliminations/'
        self.client = Client(enforce_csrf_checks=True); self.client.force_login(self.admin)
        self.token = self.client.get('/api/v1/auth/csrf/').json()['data']['csrf_token']
        self.body = {'round_number': 1, 'source_versions': self.plan['source_versions'], 'participant_statuses': self.plan['participant_statuses'],
                     'participant_ids': [row['participant_id'] for row in self.plan['candidates']], 'confirmed': True}

    def post(self, body):
        return self.client.post(self.url, body, content_type='application/json', HTTP_X_CSRFTOKEN=self.token)

    def test_admin_session_csrf_and_strict_confirmed_elimination(self):
        self.assertEqual(self.client.post(self.url, self.body, content_type='application/json').status_code, 403)
        for who in (None, self.users[0]):
            client = Client(enforce_csrf_checks=True)
            if who: client.force_login(who)
            self.assertEqual(client.post(self.url, self.body, content_type='application/json', HTTP_X_CSRFTOKEN=self.token).status_code, 403)
        for body in (self.body | {'confirmed': False}, self.body | {'participant_ids': self.body['participant_ids'][:3]},
                     self.body | {'participant_ids': [self.body['participant_ids'][0]] * 4}, self.body | {'penalty': 10},
                     self.body | {'round_number': True}, self.body | {'participant_statuses': []},
                     {k: v for k, v in self.body.items() if k != 'participant_statuses'}):
            self.assertEqual(self.post(body).status_code, 400)
            self.assertEqual(EliminationRecord.objects.count(), 0)
            self.assertFalse(self.t.participants.filter(eliminated_after_round__isnull=False).exists())
        response = self.post(self.body)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(response.json()['data']['remaining_count'], 4)
        self.assertEqual(self.post(self.body).status_code, 409)
        current = self.client.get(f'/api/v1/tournaments/{self.t.pk}/workspace/').json()['data']
        self.assertEqual(len(current['eliminations']), 1)
        self.assertEqual(sum(row['eliminated_after_round'] == 1 for row in current['standings']), 4)

    def test_api_rejects_withdrawn_swiss_but_keeps_existing_swiss_label(self):
        url = '/api/v1/tournaments/'
        response = self.client.post(url, {'name': '瑞士新赛事', 'round_count': 2, 'pairing_strategy': SWISS_REPEATS},
                                    content_type='application/json', HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(response.status_code, 400)
        old = self.existing_swiss(8, 2, strategy=SWISS_REPEATS)
        data = self.client.get(f'/api/v1/tournaments/{old.pk}/').json()['data']
        self.assertEqual(data['pairing_strategy'], SWISS_REPEATS)


class EliminationConcurrencyTests(EventFixtures, TransactionTestCase):
    race = competition_fixtures.CompetitionConcurrencyTests.race

    def setUp(self): self.setup_data()

    def test_parallel_elimination_commits_one_record_and_exactly_four_statuses(self):
        tournament = self.tournament(8, 2)
        self.confirm_unique(self.first(tournament))
        plan = svc.elimination_preview(tournament)
        result = self.race([lambda: self.eliminate(tournament, plan)] * 2)
        self.assertEqual(result.count('ok'), 1, result)
        self.assertEqual(EliminationRecord.objects.count(), 1)
        self.assertEqual(tournament.participants.filter(eliminated_after_round=1).count(), 4)

    def test_elimination_vs_generation_never_seats_already_eliminated_players(self):
        tournament = self.tournament(8, 2)
        self.confirm_unique(self.first(tournament))
        plan = svc.elimination_preview(tournament)
        result = self.race([lambda: self.eliminate(tournament, plan), lambda: svc.generate(tournament.pk, self.admin, 2)])
        self.assertTrue(set(result) <= {'ok', 'tournament_busy', 'elimination_not_available'}, result)
        if not tournament.rounds.filter(round_number=2).exists(): svc.generate(tournament.pk, self.admin, 2)
        second = tournament.rounds.get(round_number=2)
        eliminated = list(tournament.participants.filter(eliminated_after_round=1).values_list('pk', flat=True))
        self.assertEqual(second.seats.count(), 4 if eliminated else 8)
        self.assertFalse(second.seats.filter(participant_id__in=eliminated).exists())
        validate_round_structure(second)
