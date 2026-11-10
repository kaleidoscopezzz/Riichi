"""Small, exact four-player pairing presets; no dynamic rules or formulas."""
from collections import Counter
from functools import lru_cache
from itertools import combinations
from math import lcm

from django.core.exceptions import ValidationError

LEGACY = 'legacy_v1'
RANDOM = 'random_v1'
RANKED = 'ranked_v1'
MANUAL = 'manual_v1'
SWISS_REPEATS = 'swiss_repeats_first_v1'
SWISS_SCORES = 'swiss_scores_first_v1'
CHOICES = [(LEGACY, '历史自动分桌'), (RANDOM, '完全随机'), (RANKED, '高高碰'), (MANUAL, '手动分桌'), (SWISS_REPEATS, '瑞士轮 · 避重优先'), (SWISS_SCORES, '瑞士轮 · 积分接近优先')]
SUPPORTED_CHOICES = CHOICES[1:]
NEW_CHOICES = CHOICES[1:4]
BONUS_POLICY = 'add_table_base_bonus_v1'


def default_table_bonuses():
    return ['0', '0', '0', '0']


def canonical_table_bonuses(value):
    from .rules import canonical_oka
    if not isinstance(value, list) or len(value) != 4:
        raise ValidationError('请按A～D桌依次填写四项附加基础分。')
    result = []
    for item in value:
        if item is None:
            raise ValidationError('附加基础分不能为空；不加分请填写0。')
        try:
            result.append(canonical_oka(item))
        except ValidationError:
            raise ValidationError('附加基础分须为最多64字符的非负整数或精确十进制字符串，不使用科学计数法。') from None
    return result


def validate_table_bonuses(value):
    canonical_table_bonuses(value)


def validate_groups(groups, participant_ids):
    expected = set(participant_ids)
    if not isinstance(groups, list) or len(groups) != len(expected) // 4:
        raise ValidationError('每桌须4人，桌数须等于本赛事人数/4。')
    flattened = []
    for group in groups:
        if not isinstance(group, list) or len(group) != 4 or any(type(pk) is not int for pk in group):
            raise ValidationError('每桌须包含4名真实参赛者。')
        flattened.extend(group)
    if len(flattened) != len(set(flattened)) or set(flattened) != expected:
        raise ValidationError('分桌必须完整覆盖冻结名单，不能重复、缺人或加入其他赛事选手。')
    return groups


def encounters(previous_groups):
    result = Counter()
    for group in previous_groups:
        for a, b in combinations(sorted(group), 2):
            result[a, b] += 1
    return result


def repeated_pairs(groups, meetings):
    pairs = [meetings.get(tuple(sorted(pair)), 0) for group in groups for pair in combinations(group, 2)]
    return {'repeat_pairs': sum(count > 0 for count in pairs), 'repeat_encounters': sum(pairs)}


def swiss_groups(seed, scores, meetings, *, repeats_first):
    """Exact minimum-cost partition for 4/8/12/16; seed order resolves equal costs.

    Anchor each candidate group on the lowest remaining seed position, avoiding
    table permutations. Memoisation bounds a 16-player search to small subsets.
    Fractions are scaled by one shared denominator before any cost comparison.
    """
    if len(seed) not in (4, 8, 12, 16) or len(set(seed)) != len(seed):
        raise ValidationError('瑞士轮需要4、8、12或16名不重复的选手。')
    denominator = lcm(*(scores[pk].denominator for pk in seed))
    scaled = [scores[pk].numerator * (denominator // scores[pk].denominator) for pk in seed]
    costs = {}
    for group in combinations(range(len(seed)), 4):
        repeated = sum(meetings.get(tuple(sorted((seed[a], seed[b]))), 0) for a, b in combinations(group, 2))
        distance = sum(abs(scaled[a] - scaled[b]) for a, b in combinations(group, 2))
        costs[group] = (repeated, distance) if repeats_first else (distance, repeated)

    @lru_cache(maxsize=None)
    def solve(mask):
        if mask == 0:
            return (0, 0), ()
        positions = [i for i in range(len(seed)) if mask & (1 << i)]
        first = positions[0]
        best = None
        for rest in combinations(positions[1:], 3):
            group = (first, *rest)
            group_mask = sum(1 << i for i in group)
            remaining_cost, remaining_groups = solve(mask ^ group_mask)
            group_cost = costs[group]
            candidate = ((group_cost[0] + remaining_cost[0], group_cost[1] + remaining_cost[1]), (group, *remaining_groups))
            if best is None or candidate < best:
                best = candidate
        return best

    _, groups = solve((1 << len(seed)) - 1)
    return [[seed[i] for i in group] for group in groups]
