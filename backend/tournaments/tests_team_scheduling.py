from collections import Counter
import random

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from .team_scheduling import balanced_groups, match_count, schedule


class TeamScheduleTests(SimpleTestCase):
    def test_variable_team_counts_and_equal_appearances_with_four_distinct_teams(self):
        for count in (4, 5, 6, 7, 8, 12, 20, 32, 64):
            ids = list(range(1, count + 1))
            groups = balanced_groups(ids, 4, rng=random.Random(42))
            self.assertEqual(len(groups), count)
            self.assertTrue(all(len(group) == len(set(group)) == 4 for group in groups))
            self.assertEqual(Counter(pk for group in groups for pk in group), Counter({pk: 4 for pk in ids}))

    def test_fixed_positions_repeat_in_order_and_every_team_has_two_games_per_position(self):
        positions = ['先锋', '次峰', '中间', '副将', '大将']
        for count, expected in ((4, 20), (6, 30), (8, 40)):
            rows = schedule(list(range(count)), mode='positions', positions=positions, cycles=2, rng=random.Random(1))
            self.assertEqual(len(rows), expected)
            stages = sorted({row['stage_number'] for row in rows})
            self.assertEqual(stages, list(range(1, 11)))
            for stage in stages:
                games = [row for row in rows if row['stage_number'] == stage]
                self.assertEqual({row['position_label'] for row in games}, {positions[(stage - 1) % 5]})
                self.assertEqual(Counter(pk for row in games for pk in row['team_ids']), Counter({pk: 2 for pk in range(count)}))

    def test_odd_teams_two_games_rejected_but_four_games_valid_without_silent_adjustment(self):
        for count in (5, 7):
            with self.assertRaises(ValidationError) as error:
                schedule(list(range(count)), mode='positions', games_per_position=2)
            self.assertIn(f'{count * 2}个席位', str(error.exception))
            self.assertIn('4场', str(error.exception))
            rows = schedule(list(range(count)), mode='positions', games_per_position=4)
            self.assertEqual(len(rows), count * 5)
            self.assertTrue(all(len(set(row['team_ids'])) == 4 for row in rows))

    def test_free_total_is_table_matches_not_rounds_or_team_matches(self):
        rows = schedule(list(range(5)), mode='free', total_matches=10)
        self.assertEqual(len(rows), 10)
        self.assertEqual(Counter(pk for row in rows for pk in row['team_ids']), Counter({pk: 8 for pk in range(5)}))
        self.assertTrue(all(row['stage_number'] is None for row in rows))
        with self.assertRaises(ValidationError):
            schedule(list(range(5)), mode='free', total_matches=6)

    def test_invalid_inputs_and_technical_capacity_do_not_coerce_values(self):
        for invalid in (0, -1, True, 2.0, '2'):
            with self.assertRaises(ValidationError):
                schedule([1, 2, 3, 4], mode='positions', games_per_position=invalid)
        for ids in ([1, 2, 3], [1, 1, 2, 3]):
            with self.assertRaises(ValidationError): balanced_groups(ids, 4)
        with self.assertRaises(ValidationError):
            match_count(256, mode='positions', total_matches=None, positions=['先锋'] * 2, games_per_position=100, cycles=100)
