from copy import deepcopy
from fractions import Fraction
from itertools import combinations
from time import perf_counter
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.test import Client, SimpleTestCase, TestCase
from rest_framework.exceptions import ValidationError

from .pairing import LEGACY, RANDOM, RANKED, MANUAL, SWISS_REPEATS, SWISS_SCORES, canonical_table_bonuses, encounters, repeated_pairs, swiss_groups, validate_groups
from .pairing_plan import preview as pairing_preview
from .competition_services import generate, correct_result, preview_result, source_versions, ranking, finish
from .models import Tournament, RoundSeat, TableResult, TournamentMachineReservation
from .scoring import unpack
from .services import TournamentConflict, mutate_tournament
from .tests_competition import Fixtures


class PairingAlgorithmTests(SimpleTestCase):
    def test_swiss_priorities_choose_different_optimal_groups(self):
        seed = list(range(8))
        scores = {pk: Fraction(100 - pk * 10) for pk in seed}
        meetings = encounters([seed[:4], seed[4:]])
        close = swiss_groups(seed, scores, meetings, repeats_first=False)
        avoid = swiss_groups(seed, scores, meetings, repeats_first=True)
        self.assertEqual(close, [seed[:4], seed[4:]])
        self.assertEqual(repeated_pairs(close, meetings)['repeat_pairs'], 12)
        self.assertEqual(repeated_pairs(avoid, meetings)['repeat_pairs'], 4)

    def test_swiss_exact_cost_matches_all_eight_player_partitions(self):
        seed = list(range(8))
        scores = {pk: Fraction(pk * 11 + 1, 10**30 + pk + 1) for pk in seed}
        meetings = encounters([[0, 2, 4, 6], [1, 3, 5, 7], [0, 1, 2, 3], [4, 5, 6, 7]])
        def cost(groups, repeats_first):
            repeat = sum(meetings.get(tuple(sorted(pair)), 0) for group in groups for pair in combinations(group, 2))
            gap = sum((abs(scores[a] - scores[b]) for group in groups for a, b in combinations(group, 2)), Fraction())
            return (repeat, gap) if repeats_first else (gap, repeat)
        partitions = []
        for rest in combinations(seed[1:], 3):
            first = [0, *rest]
            partitions.append([first, [pk for pk in seed if pk not in first]])
        for priority in [True, False]:
            grouped = swiss_groups(seed, scores, meetings, repeats_first=priority)
            self.assertEqual(cost(grouped, priority), min(cost(groups, priority) for groups in partitions))

    def test_sixteen_can_avoid_repeats_and_search_is_bounded(self):
        seed = list(range(16))
        previous = [seed[index:index+4] for index in range(0, 16, 4)]
        meetings = encounters(previous)
        start = perf_counter()
        groups = swiss_groups(seed, {pk: Fraction(0) for pk in seed}, meetings, repeats_first=True)
        self.assertLess(perf_counter() - start, 10)
        self.assertEqual(repeated_pairs(groups, meetings)['repeat_pairs'], 0)
        self.assertEqual(sorted(pk for group in groups for pk in group), seed)
        self.assertEqual(swiss_groups(seed, {pk: Fraction(0) for pk in seed}, meetings, repeats_first=True), groups)

    def test_four_player_repeats_are_reported_honestly(self):
        seed = list(range(4))
        meetings = encounters([seed])
        grouped = swiss_groups(seed, {pk: Fraction(0) for pk in seed}, meetings, repeats_first=True)
        self.assertEqual(repeated_pairs(grouped, meetings), {'repeat_pairs': 6, 'repeat_encounters': 6})

    def test_manual_groups_and_exact_nonnegative_bonuses_are_strict(self):
        for groups in [[[1, 2, 3]], [[1, 2, 3, 3]], [[1, 2, 3, True]], [[1, 2, 3, 5]]]:
            with self.assertRaises(ModelValidationError): validate_groups(groups, [1, 2, 3, 4])
        self.assertEqual(canonical_table_bonuses(['+0005.125', 0, '0.000', '0']), ['5.125', '0', '0', '0'])
        for bonuses in [[1, 2], [None, 0, 0, 0], [-1, 0, 0, 0], [True, 0, 0, 0], [0.1, 0, 0, 0], ['1e2', 0, 0, 0]]:
            with self.assertRaises(ModelValidationError): canonical_table_bonuses(bonuses)


class PairingWorkflowTests(Fixtures, TestCase):
    def setUp(self): self.setup_data()

    def test_manual_preview_does_not_write_and_exact_dragged_groups_are_persisted(self):
        t = self.tournament(8, 2, pairing_strategy=MANUAL)
        t.refresh_from_db()
        revision = t.revision
        plan = pairing_preview(t.pk, self.admin, 1)
        self.assertFalse(t.rounds.exists())
        self.assertFalse(TournamentMachineReservation.objects.exists())
        t.refresh_from_db(); self.assertEqual(t.revision, revision)
        groups = [list(table['participant_ids']) for table in plan['tables']]
        groups[0][0], groups[1][0] = groups[1][0], groups[0][0]
        round_ = generate(t.pk, self.admin, 1, machine_ids=[machine.pk for machine in self.machines[:2]], pairing_token=plan['token'], participant_groups=groups)
        self.assertEqual([set(table.seats.values_list('participant_id', flat=True)) for table in round_.tables.all()], list(map(set, groups)))
        self.assertEqual(round_.generation_snapshot['pairing']['groups'], groups)
        self.assertTrue(round_.generation_snapshot['pairing']['manual'])
        with self.assertRaises(TournamentConflict):
            generate(t.pk, self.admin, 1, pairing_token=plan['token'], participant_groups=groups)

    def test_signed_random_preview_matches_generation_and_rejects_tampering(self):
        t = self.tournament(8, pairing_strategy=RANDOM)
        plan = pairing_preview(t.pk, self.admin, 1)
        with self.assertRaises(ValidationError):
            generate(t.pk, self.admin, 1, machine_ids=[machine.pk for machine in self.machines[:2]], pairing_token=plan['token'] + 'bad')
        self.assertFalse(t.rounds.exists())
        round_ = generate(t.pk, self.admin, 1, machine_ids=[machine.pk for machine in self.machines[:2]], pairing_token=plan['token'])
        self.assertEqual([set(table.seats.values_list('participant_id', flat=True)) for table in round_.tables.all()], [set(table['participant_ids']) for table in plan['tables']])

    def test_preview_is_bound_to_admin_and_manual_cannot_cover_foreign_or_duplicate_ids(self):
        t = self.tournament(8, pairing_strategy=MANUAL)
        plan = pairing_preview(t.pk, self.admin, 1)
        groups = [table['participant_ids'][:] for table in plan['tables']]
        other = get_user_model().objects.create_user(username='pairing_other_admin', is_staff=True)
        with self.assertRaises(ValidationError):
            generate(t.pk, other, 1, machine_ids=[machine.pk for machine in self.machines[:2]], pairing_token=plan['token'], participant_groups=groups)
        groups[0][0] = groups[1][0]
        with self.assertRaises(ValidationError):
            generate(t.pk, self.admin, 1, machine_ids=[machine.pk for machine in self.machines[:2]], pairing_token=plan['token'], participant_groups=groups)
        self.assertFalse(t.rounds.exists())

    def test_correction_invalidates_pairing_preview_without_changing_old_round(self):
        t = self.tournament(8, 2, pairing_strategy=SWISS_REPEATS)
        first = self.first(t)
        for table in first.tables.all(): self.confirm(table)
        plan = pairing_preview(t.pk, self.admin, 2)
        old = deepcopy(first.generation_snapshot)
        table = first.tables.first()
        values = [{'participant_id': seat.participant_id, 'raw_points': 25000} for seat in table.seats.all()]
        correct_result(table.pk, self.admin, 1, points=values)
        with self.assertRaises(TournamentConflict) as error:
            generate(t.pk, self.admin, 2, pairing_token=plan['token'])
        self.assertEqual(error.exception.default_code, 'stale_pairing')
        first.refresh_from_db(); self.assertEqual(first.generation_snapshot, old)
        self.assertEqual(t.rounds.count(), 1)

    def test_high_table_bonus_is_zero_first_round_then_exact_and_shared_by_every_player(self):
        bonus = '5.123456789012345678901234567890123456789'
        t = self.tournament(8, 2, pairing_strategy=RANKED, ranked_table_bonuses=[bonus, '2', '0', '0'])
        first = self.first(t)
        self.assertEqual(list(first.tables.values_list('base_bonus', flat=True)), ['0', '0'])
        for table in first.tables.all(): self.confirm(table, [25000] * 4)
        plan = pairing_preview(t.pk, self.admin, 2)
        second = generate(t.pk, self.admin, 2, pairing_token=plan['token'])
        for index, table in enumerate(second.tables.all()):
            expected = Fraction(bonus if index == 0 else '2')
            pending = preview_result(table.pk, 0, [{'participant_id': seat.participant_id, 'raw_points': 25000} for seat in table.seats.all()])
            self.assertEqual([unpack(row['score']) for row in pending['scores']], [expected] * 4)
            confirmed = self.confirm(table, [25000] * 4)
            self.assertEqual(confirmed['rules']['table_bonus_policy'], 'add_table_base_bonus_v1')
            self.assertEqual(confirmed['rules']['table_base_bonus'], bonus if index == 0 else '2')
            self.assertEqual([unpack(row['score']) for row in confirmed['scores']], [expected] * 4)
        total = sum((unpack(row['total']) for row in ranking(t)[0]), Fraction())
        self.assertEqual(total, 4 * (Fraction(bonus) + 2))
        table = second.tables.first()
        corrected = correct_result(table.pk, self.admin, 1, points=[{'participant_id': seat.participant_id, 'raw_points': raw} for seat, raw in zip(table.seats.order_by('id'), [40000, 30000, 20000, 10000])])
        self.assertEqual(corrected['rules']['table_base_bonus'], bonus)
        self.assertEqual(unpack(corrected['scores'][0]['base']), 10 + Fraction(bonus))
        self.resolve(t)
        final = finish(t.pk, self.admin, source_versions(t))
        self.assertEqual(final['rules']['ranked_table_bonuses'], [bonus, '2', '0', '0'])
        self.assertFalse(TournamentMachineReservation.objects.filter(table__tournament=t, status='active').exists())

    def test_expired_wrong_tournament_and_wrong_round_tokens_are_rejected(self):
        from django.core import signing
        t = self.tournament(8, 2, pairing_strategy=MANUAL)
        plan = pairing_preview(t.pk, self.admin, 1)
        groups = [table['participant_ids'][:] for table in plan['tables']]
        with patch('tournaments.pairing_plan.signing.loads', side_effect=signing.SignatureExpired('expired')):
            with self.assertRaises(ValidationError): generate(t.pk, self.admin, 1, machine_ids=[m.pk for m in self.machines[:2]], pairing_token=plan['token'], participant_groups=groups)
        other = self.tournament(8, 2, pairing_strategy=MANUAL)
        with self.assertRaises(ValidationError): generate(other.pk, self.admin, 1, machine_ids=[m.pk for m in self.machines[:2]], pairing_token=plan['token'], participant_groups=groups)
        payload = signing.loads(plan['token'], salt='tournaments.pairing-plan.v1')
        payload['number'] = 2
        wrong = signing.dumps(payload, salt='tournaments.pairing-plan.v1', compress=True)
        with self.assertRaises(ValidationError): generate(t.pk, self.admin, 1, machine_ids=[m.pk for m in self.machines[:2]], pairing_token=wrong, participant_groups=groups)
        self.assertFalse(t.rounds.exists())

    def test_only_new_event_draft_selects_strategy_and_started_config_is_frozen(self):
        t = self.tournament(pairing_strategy=SWISS_SCORES)
        with self.assertRaises(TournamentConflict): mutate_tournament(t.pk, values={'pairing_strategy': RANDOM})
        legacy = Tournament.objects.create(name='旧规则QA', round_count=1, created_by=self.admin, pairing_strategy=LEGACY, table_bonus_policy='none')
        with self.assertRaises(ValidationError): mutate_tournament(legacy.pk, values={'ranked_table_bonuses': ['1', '0', '0', '0']})
        legacy.refresh_from_db(); self.assertEqual(legacy.ranked_table_bonuses, ['0'] * 4)

    def test_swiss_preview_and_generate_are_admin_csrf_protected(self):
        t = self.tournament(8, pairing_strategy=SWISS_SCORES)
        url = f'/api/v1/tournaments/{t.pk}/rounds/preview/'
        client = Client(enforce_csrf_checks=True); client.force_login(self.admin)
        self.assertEqual(client.post(url, {'round_number': 1}, content_type='application/json').status_code, 403)
        token = client.get('/api/v1/auth/csrf/').json()['data']['csrf_token']
        response = client.post(url, {'round_number': 1}, content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response['Cache-Control'], 'no-store')
        client.force_login(self.users[0])
        self.assertEqual(client.post(url, {'round_number': 1}, content_type='application/json', HTTP_X_CSRFTOKEN=token).status_code, 403)
