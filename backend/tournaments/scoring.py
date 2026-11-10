"""Versioned, lossless authority. JSON fractions contain decimal integer strings."""
from fractions import Fraction
from django.core.exceptions import ValidationError as ModelValidationError
from rest_framework.exceptions import ValidationError

from .rules import canonical_oka
from .pairing import BONUS_POLICY, LEGACY, RANKED, SUPPORTED_CHOICES, canonical_table_bonuses


def pack(value):
    value = Fraction(value)
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def unpack(value):
    return Fraction(int(value['numerator']), int(value['denominator']))


def rules(tournament, *, table=None):
    if (tournament.score_tie_policy, tournament.champion_tiebreak_policy) != ('split_rank_bonus_v1', 'performance_v1') or tournament.rules_version not in (1, 2):
        raise ValidationError({'rules_version': ['不支持此冻结策略或版本。']})
    if tournament.rules_version == 1 and tournament.oka_override is not None:
        raise ValidationError({'rules_version': ['自定义头名赏 Oka 需要规则版本 2。']})
    snapshot = {key: getattr(tournament, key) for key in ['starting_points', 'return_points', 'uma', 'score_tie_policy', 'champion_tiebreak_policy', 'rules_version', 'rules_source']}
    if tournament.rules_version == 2:
        try:
            override = canonical_oka(tournament.oka_override)
        except ModelValidationError as exc:
            raise ValidationError({'oka_override': exc.messages}) from None
        snapshot.update(oka_override=override, oka=tournament.oka if override is None else override)
    strategy = getattr(tournament, 'pairing_strategy', LEGACY)
    if strategy != LEGACY:
        if strategy not in dict(SUPPORTED_CHOICES) or tournament.table_bonus_policy != BONUS_POLICY:
            raise ValidationError({'pairing_strategy': ['不支持此冻结分桌或附加积分策略。']})
        try:
            bonuses = canonical_table_bonuses(tournament.ranked_table_bonuses)
        except ModelValidationError as exc:
            raise ValidationError({'ranked_table_bonuses': exc.messages}) from None
        snapshot.update(pairing_strategy=strategy, table_bonus_policy=BONUS_POLICY, ranked_table_bonuses=bonuses)
        if table is not None:
            expected = bonuses[table.table_number - 1] if strategy == RANKED and table.round.round_number > 1 else '0'
            if table.base_bonus != expected:
                raise ValidationError({'ranked_table_bonuses': ['本桌附加基础分与冻结赛事配置不符。']})
            snapshot.update(table_base_bonus=expected, table_bonus_source=table.bonus_source)
    elif table is not None and table.base_bonus != '0':
        raise ValidationError({'ranked_table_bonuses': ['历史赛事不支持附加基础分。']})
    return snapshot


def score(tournament, points, *, table=None):
    snapshot = rules(tournament, table=table)
    bonus = [Fraction(x) for x in tournament.uma]
    bonus[0] += Fraction(4 * (tournament.return_points - tournament.starting_points), 1000) if tournament.rules_version == 1 else Fraction(snapshot['oka'])
    ordered = sorted(points.items(), key=lambda row: -row[1])
    results = []
    i = 0
    while i < 4:
        j = i + 1
        while j < 4 and ordered[j][1] == ordered[i][1]:
            j += 1
        reward = sum(bonus[i:j], Fraction()) / (j - i)
        for participant, raw in ordered[i:j]:
            base = Fraction(raw - tournament.return_points, 1000) + Fraction(snapshot.get('table_base_bonus', '0'))
            results.append({'participant_id': int(participant), 'raw_points': raw, 'rank': i + 1, 'tied': j - i > 1, 'base': pack(base), 'bonus': pack(reward), 'score': pack(base + reward)})
        i = j
    return results
