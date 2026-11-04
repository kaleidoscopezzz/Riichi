"""Versioned, lossless authority. JSON fractions contain decimal integer strings."""
from fractions import Fraction
from rest_framework.exceptions import ValidationError


def pack(value):
    value = Fraction(value)
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def unpack(value):
    return Fraction(int(value['numerator']), int(value['denominator']))


def rules(tournament):
    if (tournament.score_tie_policy, tournament.champion_tiebreak_policy, tournament.rules_version) != ('split_rank_bonus_v1', 'performance_v1', 1):
        raise ValidationError({'rules_version': ['不支持此冻结策略或版本。']})
    return {key: getattr(tournament, key) for key in ['starting_points', 'return_points', 'uma', 'score_tie_policy', 'champion_tiebreak_policy', 'rules_version', 'rules_source']}


def score(tournament, points):
    rules(tournament)
    bonus = [Fraction(x) for x in tournament.uma]
    bonus[0] += Fraction(4 * (tournament.return_points - tournament.starting_points), 1000)
    ordered = sorted(points.items(), key=lambda row: -row[1])
    results = []
    i = 0
    while i < 4:
        j = i + 1
        while j < 4 and ordered[j][1] == ordered[i][1]:
            j += 1
        reward = sum(bonus[i:j], Fraction()) / (j - i)
        for participant, raw in ordered[i:j]:
            base = Fraction(raw - tournament.return_points, 1000)
            results.append({'participant_id': int(participant), 'raw_points': raw, 'rank': i + 1, 'tied': j - i > 1, 'base': pack(base), 'bonus': pack(reward), 'score': pack(base + reward)})
        i = j
    return results
