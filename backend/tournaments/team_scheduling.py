"""Four distinct teams per match; exact seat arithmetic, no scoring shortcuts."""
import random

from rest_framework.exceptions import ValidationError

POSITIONS = ['先锋', '次峰', '中间', '副将', '大将']
MAX_MATCHES = 10000
MAX_TEAMS = 256
MAX_MEMBERS = 4096


def default_positions():
    return list(POSITIONS)


def match_count(team_count, *, mode, total_matches, positions, games_per_position, cycles):
    if type(team_count) is not int or not 4 <= team_count <= MAX_TEAMS:
        raise ValidationError({'teams': ['正式编排需要至少四支队伍。']})
    if mode == 'free':
        if type(total_matches) is not int or not 1 <= total_matches <= MAX_MATCHES:
            raise ValidationError({'total_matches': ['总桌场次须为1～10000的整数。']})
        if 4 * total_matches % team_count:
            raise ValidationError({'total_matches': [f'{team_count}队、{total_matches}桌场不能做到各队等场；请调整总桌场次。']})
        return total_matches
    if mode != 'positions':
        raise ValidationError({'schedule_mode': ['请选择自由场次或固定位置循环。']})
    if not isinstance(positions, list) or not 1 <= len(positions) <= 32 or any(not isinstance(p, str) or not p.strip() or len(p) > 80 for p in positions) or len(set(positions)) != len(positions):
        raise ValidationError({'positions': ['位置须为1～32个不重复的非空名称。']})
    if type(games_per_position) is not int or not 1 <= games_per_position <= 100 or type(cycles) is not int or not 1 <= cycles <= 100:
        raise ValidationError({'games_per_position': ['每位置场数和循环次数须为1～100的整数。']})
    if team_count * games_per_position % 4:
        suggested = next(k for k in range(games_per_position + 1, games_per_position + 5) if team_count * k % 4 == 0)
        raise ValidationError({'games_per_position': [f'{team_count}队×每队{games_per_position}场＝{team_count * games_per_position}个席位，不能完整分成四人桌；可改为每位置{suggested}场。']})
    count = team_count * games_per_position * len(positions) * cycles // 4
    if count > MAX_MATCHES:
        raise ValidationError({'cycles': ['本次配置超过10000桌场的编排处理容量，请减少循环或场数。']})
    return count


def balanced_groups(team_ids, appearances, *, rng=None):
    """Every team appears exactly E times; every four consecutive seats differ."""
    ids = list(team_ids)
    if len(ids) < 4 or len(ids) != len(set(ids)) or type(appearances) is not int or appearances < 1 or len(ids) * appearances % 4:
        raise ValidationError({'teams': ['队伍和场次数不能组成完整均衡赛程。']})
    (rng or random.SystemRandom()).shuffle(ids)
    seats = ids * appearances
    return [seats[index:index + 4] for index in range(0, len(seats), 4)]


def schedule(team_ids, *, mode, total_matches=None, positions=None, games_per_position=2, cycles=1, rng=None):
    positions = default_positions() if positions is None else positions
    count = match_count(len(team_ids), mode=mode, total_matches=total_matches, positions=positions,
                        games_per_position=games_per_position, cycles=cycles)
    result = []
    if mode == 'free':
        for group in balanced_groups(team_ids, count * 4 // len(team_ids), rng=rng):
            result.append({'stage_number': None, 'cycle': None, 'position_index': None, 'position_label': '', 'team_ids': group})
    else:
        for cycle in range(1, cycles + 1):
            for index, position in enumerate(positions):
                for group in balanced_groups(team_ids, games_per_position, rng=rng):
                    result.append({'stage_number': (cycle - 1) * len(positions) + index + 1, 'cycle': cycle,
                                   'position_index': index + 1, 'position_label': position, 'team_ids': group})
    return result
