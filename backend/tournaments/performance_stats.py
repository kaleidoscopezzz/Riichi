"""Display statistics derived solely from saved confirmed scores, never rank keys."""
from fractions import Fraction

from .scoring import pack, unpack


def add_statistics(rows):
    for row in rows:
        rounds = row.get('rounds', [])
        row['highest_raw_points'] = max((item['raw_points'] for item in rounds), default=None)
        row['fourth_count'] = sum(item['rank'] == 4 for item in rounds)
        row['fourth_avoidance_rate'] = pack(Fraction(len(rounds) - row['fourth_count'], len(rounds))) if rounds else None
    # Older minimal final snapshots cannot substantiate per-half statistics.
    played = [row for row in rows if row.get('rounds')]

    def leaders(key, *, exact=False, positive=False):
        if not played:
            return {'value': None, 'participant_ids': []}
        def value_of(row):
            return unpack(row[key]) if exact else row.get(key, sum(item['rank'] == 1 for item in row.get('rounds', [])))
        value = max(value_of(row) for row in played)
        if positive and not value:
            return {'value': None, 'participant_ids': []}
        return {'value': pack(value) if exact else value,
                'participant_ids': [row['participant_id'] for row in played if value_of(row) == value]}

    return {'fourth_avoidance': leaders('fourth_avoidance_rate', exact=True),
            'highest_raw_points': leaders('highest_raw_points'),
            'most_firsts': leaders('first_count', positive=True)}
