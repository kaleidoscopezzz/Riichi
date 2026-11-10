"""Team rosters, versioned plans, stages and batches within the tournament module."""
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from fractions import Fraction
from itertools import groupby
import random

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import OperationalError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from machines.models import MahjongMachine
from players.models import PlayerProfile
from .models import (Tournament, TournamentParticipant, TournamentRound, RoundTable, RoundSeat,
                     TournamentTable, TournamentMachineReservation as Reservation, TableResult, LotteryRecord,
                     TournamentTeam, TeamMember, TeamCompetitionSettings, TeamStage, TeamStageRepresentative,
                     TeamMatchPlan, TeamAuditRecord)
from .pairing import TEAM_BALANCED, TEAM_MANUAL, TEAM_CHOICES
from .rules import canonical_oka, canonical_uma
from .scoring import pack, unpack, rules
from .services import TournamentConflict, database_busy
from .team_scheduling import schedule, match_count, default_positions, MAX_TEAMS, MAX_MEMBERS, MAX_MATCHES

SALT_SCHEDULE = 'riichi.team-schedule.v1'
SALT_BATCH = 'riichi.team-batch.v1'


def conflict(message, code):
    raise TournamentConflict(message, code)


def require_team(t):
    if t.competition_type != 'team':
        conflict('此操作适用于团队赛。', 'competition_mode_mismatch')


@contextmanager
def team_locked(pk, *, status=None, revision=None):
    from .competition_services import locked
    with locked(pk, writable=False) as (t, machines):
        require_team(t)
        if t.status == 'completed':
            conflict('团队赛已完赛，结果与计划只读。', 'tournament_completed')
        if status and t.status != status:
            conflict('当前赛事状态不允许此操作。', 'tournament_frozen')
        if revision is not None and revision != t.revision - 1:
            conflict('团队赛配置或出场计划已变化，请刷新后核对。', 'stale_tournament')
        yield t, machines


def audit(t, user, action, before, after, reason=''):
    return TeamAuditRecord.objects.create(tournament=t, created_by=user, action=action, revision=t.revision,
                                         before_snapshot=before, after_snapshot=after, reason=reason)


def active_teams(t):
    return list(t.teams.filter(active=True).prefetch_related('members__participant__player__user').order_by('id'))


def roster(t, *, teams=None):
    teams = active_teams(t) if teams is None else teams
    rows = []
    for team in teams:
        members = [m for m in team.members.all() if m.active]
        rows.append({'id': team.pk, 'name': team.name if t.status == 'draft' else team.name_snapshot,
                     'members': [{'id': m.pk, 'participant_id': m.participant_id, 'player_id': m.participant.player_id,
                                  'display_name': m.participant.player.nickname if t.status == 'draft' else m.participant.display_name_snapshot,
                                  'is_active': m.participant.player.user.is_active, 'is_captain': m.is_captain}
                                 for m in members]})
    return rows


def roster_source(t, *, teams=None):
    # Account archival is not a change to frozen competition membership.
    return source_from_roster(roster(t, teams=teams))


def source_from_roster(rows):
    return [{**team, 'members': [{k: v for k, v in member.items() if k != 'is_active'} for member in team['members']]}
            for team in rows]


def config_data(settings):
    return {key: getattr(settings, key) for key in ['schedule_mode', 'total_matches', 'positions', 'games_per_position', 'cycles', 'schedule_revision']}


def plan_query(t):
    return t.team_matches.filter(schedule_revision=t.team_settings.schedule_revision).exclude(status='voided').select_related('stage', 'table__round').order_by('match_number')


def plan_sources(plans):
    return [{'match_id': p.pk, 'version': p.version} for p in plans]


def plan_snapshot(p):
    return {'id': p.pk, 'match_number': p.match_number, 'schedule_revision': p.schedule_revision, 'version': p.version,
            'stage_id': p.stage_id, 'team_ids': list(p.team_ids), 'lineup': dict(p.lineup), 'status': p.status,
            'captain_supplied': p.captain_supplied, 'confirmed_by': p.confirmed_by_id,
            'confirmed_at': p.confirmed_at.isoformat() if p.confirmed_at else None, 'table_id': p.table_id}


def plan_data(p, teams, confirmed=None):
    by_team = {team['id']: team for team in teams}
    rows = []
    for team_id in p.team_ids:
        team = by_team.get(team_id)
        member_id = p.lineup.get(str(team_id))
        member = next((m for m in (team['members'] if team else []) if m['id'] == member_id), None)
        rows.append({'team_id': team_id, 'team_name': team['name'] if team else '历史队伍', 'member_id': member_id,
                     'participant_id': member['participant_id'] if member else None,
                     'display_name': member['display_name'] if member else None})
    done = p.table_id in (confirmed or {})
    return {**plan_snapshot(p), 'status': 'completed' if done else p.status, 'lineup_rows': rows,
            'cycle': p.stage.cycle if p.stage_id else None, 'position_index': p.stage.position_index if p.stage_id else None,
            'position_label': p.stage.position_label if p.stage_id else '',
            'batch_number': p.table.round.round_number if p.table_id else None}


def validate_profiles(ids):
    if len(ids) > MAX_MEMBERS or len(ids) != len(set(ids)):
        raise ValidationError({'teams': ['全赛成员不能重复，处理容量为4096名成员。']})
    users = list(get_user_model().objects.select_for_update().filter(player_profile__id__in=ids).order_by('pk'))
    profiles = list(PlayerProfile.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
    if len(profiles) != len(ids) or any(not u.is_active or u.is_staff or u.is_superuser for u in users):
        raise ValidationError({'teams': ['成员包含已归档、不存在的选手或管理员档案。']})
    return {p.pk: p for p in profiles}


def replace_roster(t, rows):
    if len(rows) > MAX_TEAMS:
        raise ValidationError({'teams': ['队伍处理容量为256支，请减少单赛队伍数量。']})
    names = [row['name'].strip() for row in rows]
    if any(not name or len(name) > 80 for name in names) or len(set(names)) != len(names):
        raise ValidationError({'teams': ['队伍名称须非空且本赛事内不重复，最多80字。']})
    ids = [pk for row in rows for pk in row['player_ids']]
    validate_profiles(ids)
    existing = {team.pk: team for team in t.teams.all()}
    supplied = [row['id'] for row in rows if row.get('id') is not None]
    if len(supplied) != len(set(supplied)) or any(pk not in existing for pk in supplied):
        raise ValidationError({'teams': ['队伍ID重复或不属于本赛事。']})
    # Archived draft membership is kept when a previous plan/audit referenced it.
    t.teams.update(active=False)
    TeamMember.objects.filter(participant__tournament=t).update(active=False, is_captain=False)
    entries = {p.player_id: p for p in t.participants.all()}
    memberships = {m.participant_id: m for m in TeamMember.objects.filter(participant__tournament=t)}
    for row, name in zip(rows, names):
        team = existing.get(row.get('id'))
        if team is None:
            team = TournamentTeam.objects.create(tournament=t, name=name)
        else:
            team.name, team.active = name, True
            team.save(update_fields=['name', 'active'])
        captain = row.get('captain_player_id')
        if captain is not None and captain not in row['player_ids']:
            raise ValidationError({'teams': ['队长标记必须属于本队成员。']})
        for player_id in row['player_ids']:
            p = entries.get(player_id)
            if p is None:
                p = TournamentParticipant.objects.create(tournament=t, player_id=player_id)
                entries[player_id] = p
            member = memberships.get(p.pk)
            if member is None:
                member = TeamMember.objects.create(team=team, participant=p)
                memberships[p.pk] = member
            member.team, member.active, member.is_captain = team, True, player_id == captain
            member.save()


def configure(t, settings, values):
    numeric = ('name', 'description', 'starting_points', 'return_points', 'uma', 'oka_override', 'pairing_strategy')
    for key in numeric:
        if key in values:
            setattr(t, key, values[key])
    try:
        t.uma = canonical_uma(t.uma)
        t.oka_override = canonical_oka(t.oka_override)
    except ModelValidationError as error:
        raise ValidationError({'rules': error.messages}) from None
    for key in ('schedule_mode', 'total_matches', 'positions', 'games_per_position', 'cycles'):
        if key in values:
            setattr(settings, key, values[key])
    if settings.schedule_mode == 'positions':
        settings.total_matches = None
    # Validate configuration independently of an incomplete draft roster.
    match_count(4, mode=settings.schedule_mode, total_matches=settings.total_matches, positions=settings.positions,
                games_per_position=settings.games_per_position, cycles=settings.cycles)
    try:
        t.full_clean()
        settings.full_clean(exclude=['tournament'])
    except ModelValidationError as error:
        raise ValidationError(getattr(error, 'message_dict', {'settings': error.messages})) from None
    rules(t)


def create_team_tournament(user, values):
    values = dict(values)
    teams = values.pop('teams', [])
    try:
        with transaction.atomic():
            # The legacy non-null column stays unchanged; team counts live in
            # settings/plans and the public team DTO never exposes this carrier.
            t = Tournament(created_by=user, name=values.get('name', ''), competition_type='team', round_count=1,
                           pairing_strategy=TEAM_BALANCED, table_bonus_policy='none', ranked_table_bonuses=['0'] * 4,
                           champion_tiebreak_policy='team_performance_v1', rules_source='created_team_v1')
            settings = TeamCompetitionSettings(tournament=t, total_matches=values.get('total_matches', 10))
            configure(t, settings, values)
            t.save(); settings.save()
            replace_roster(t, teams)
            audit(t, user, 'created', {}, {'roster': roster(t), 'settings': config_data(settings)})
            return t
    except OperationalError as error:
        database_busy(error)


def update_team_tournament(pk, values, *, user=None, revision=None):
    with team_locked(pk, status='draft', revision=revision) as (t, _):
        if plan_query(t).exists():
            conflict('修改队伍或规则前，请先显式撤回未开场赛程。', 'schedule_exists')
        before = {'roster': roster(t), 'settings': config_data(t.team_settings), 'rules': rules(t)}
        values = dict(values)
        teams = values.pop('teams', None)
        configure(t, t.team_settings, values)
        t.save(); t.team_settings.save()
        if teams is not None:
            replace_roster(t, teams)
        audit(t, user or t.created_by, 'draft_saved', before,
              {'roster': roster(t), 'settings': config_data(t.team_settings), 'rules': rules(t)})
        return t


def validate_schedule(t, plans=None):
    teams = active_teams(t)
    ids = {team.pk for team in teams}
    settings = t.team_settings
    count = match_count(len(teams), mode=settings.schedule_mode, total_matches=settings.total_matches,
                        positions=settings.positions, games_per_position=settings.games_per_position, cycles=settings.cycles)
    plans = list(plan_query(t)) if plans is None else plans
    if len(plans) != count or [p.match_number for p in plans] != list(range(1, count + 1)):
        conflict('赛程未完整编排，请先生成全部计划。', 'team_schedule_incomplete')
    for p in plans:
        if len(p.team_ids) != 4 or len(set(p.team_ids)) != 4 or any(type(pk) is not int or pk not in ids for pk in p.team_ids):
            raise ValidationError({'team_ids': ['每场必须由本赛事四支不同队伍各占一席。']})
        if settings.schedule_mode == 'positions' and (p.stage_id is None or p.stage.tournament_id != t.pk or p.stage.schedule_revision != settings.schedule_revision):
            raise ValidationError({'stage': ['固定位置计划必须属于当前赛事的当前赛程阶段。']})
        if settings.schedule_mode == 'free' and p.stage_id is not None:
            raise ValidationError({'stage': ['自由场次计划不使用位置阶段。']})
    if settings.schedule_mode == 'free':
        counts = Counter(pk for p in plans for pk in p.team_ids)
        if counts != Counter({pk: count * 4 // len(ids) for pk in ids}):
            raise ValidationError({'team_ids': ['自由赛程须各队等场，请调整计划中的四队分组。']})
    else:
        stages = list(t.team_stages.filter(schedule_revision=settings.schedule_revision).order_by('stage_number'))
        if len(stages) != len(settings.positions) * settings.cycles:
            conflict('位置循环阶段不完整。', 'team_schedule_incomplete')
        for index, stage in enumerate(stages):
            if (stage.stage_number, stage.cycle, stage.position_index, stage.position_label, stage.games_per_team) != (
                    index + 1, index // len(settings.positions) + 1, index % len(settings.positions) + 1,
                    settings.positions[index % len(settings.positions)], settings.games_per_position):
                raise ValidationError({'stage': ['位置名称、顺序、场数或循环与冻结配置不一致。']})
            counts = Counter(pk for p in plans if p.stage_id == stage.pk for pk in p.team_ids)
            if counts != Counter({pk: settings.games_per_position for pk in ids}):
                raise ValidationError({'team_ids': ['每个位置阶段须各队完成配置的相同场数。']})
    return plans


def start_team_tournament(pk, *, user=None, revision=None):
    with team_locked(pk, status='draft', revision=revision) as (t, _):
        teams = active_teams(t)
        if any(not any(m.active for m in team.members.all()) for team in teams):
            raise ValidationError({'teams': ['每支队伍至少登记一位可出场成员。']})
        members = list(TeamMember.objects.filter(team__tournament=t, team__active=True, active=True).select_related('participant'))
        profiles = validate_profiles([m.participant.player_id for m in members])
        validate_schedule(t)
        before = roster(t, teams=teams)
        for team in teams:
            team.name_snapshot = team.name
        TournamentTeam.objects.bulk_update(teams, ['name_snapshot'])
        for member in members:
            member.participant.display_name_snapshot = profiles[member.participant.player_id].nickname
        TournamentParticipant.objects.bulk_update([m.participant for m in members], ['display_name_snapshot'])
        t.status, t.started_at = 'started', timezone.now()
        t.save()
        audit(t, user or t.created_by, 'started', {'roster': before}, {'roster': roster_source(t), 'rules': rules(t)})
        return t


def load_token(token, salt):
    try:
        payload = signing.loads(token, salt=salt, max_age=1800)
        if not isinstance(payload, dict):
            raise ValueError('invalid preview')
        return payload
    except (signing.BadSignature, signing.SignatureExpired, TypeError, ValueError):
        raise ValidationError({'token': ['预览无效或已过期，请重新预览。']}) from None


def preview_schedule(pk, user):
    t = get_object_or_404(Tournament, pk=pk)
    require_team(t)
    if t.status == 'completed' or t.rounds.exists() or plan_query(t).exists():
        conflict('已有赛程请先撤回未开场计划，开场后保留原赛程。', 'schedule_exists')
    settings = config_data(t.team_settings)
    team_roster = roster_source(t)
    rows = schedule([team['id'] for team in team_roster], mode=settings['schedule_mode'], total_matches=settings['total_matches'],
                    positions=settings['positions'], games_per_position=settings['games_per_position'], cycles=settings['cycles'])
    payload = {'tournament_id': t.pk, 'user_id': user.pk, 'revision': t.revision, 'settings': settings, 'roster': team_roster, 'rows': rows, 'rules': rules(t)}
    return {'match_count': len(rows), 'games_per_team': len(rows) * 4 // len(team_roster),
            'preview_matches': [{**row, 'match_number': i + 1} for i, row in enumerate(rows[:40])],
            'preview_limit': 40, 'token': signing.dumps(payload, salt=SALT_SCHEDULE, compress=True)}


def generate_schedule(pk, user, token):
    with team_locked(pk) as (t, _):
        if t.rounds.exists() or plan_query(t).exists():
            conflict('当前赛程已生成，不能覆盖。', 'schedule_exists')
        payload = load_token(token, SALT_SCHEDULE)
        if (payload.get('tournament_id'), payload.get('user_id')) != (t.pk, user.pk):
            raise ValidationError({'token': ['赛程预览不属于本赛事或当前管理员。']})
        if payload.get('revision') != t.revision - 1 or payload.get('settings') != config_data(t.team_settings) or payload.get('roster') != roster_source(t) or payload.get('rules') != rules(t):
            conflict('队伍或配置已变化，请重新预览赛程。', 'stale_team_preview')
        rows = payload['rows']
        t.team_settings.schedule_revision += 1
        t.team_settings.save(update_fields=['schedule_revision'])
        revision = t.team_settings.schedule_revision
        stages = {}
        for row in rows:
            number = row['stage_number']
            if number is not None and number not in stages:
                stage = TeamStage.objects.create(tournament=t, schedule_revision=revision, stage_number=number,
                    cycle=row['cycle'], position_index=row['position_index'], position_label=row['position_label'], games_per_team=t.team_settings.games_per_position)
                stages[number] = stage
                TeamStageRepresentative.objects.bulk_create([TeamStageRepresentative(stage=stage, team=team) for team in active_teams(t)])
        TeamMatchPlan.objects.bulk_create([TeamMatchPlan(tournament=t, schedule_revision=revision, match_number=i + 1,
            stage=stages.get(row['stage_number']), team_ids=row['team_ids'], lineup={str(pk): None for pk in row['team_ids']}) for i, row in enumerate(rows)])
        validate_schedule(t)
        audit(t, user, 'schedule_generated', {}, {'schedule_revision': revision, 'match_count': len(rows), 'roster': roster_source(t)})
        return {'schedule_revision': revision, 'match_count': len(rows)}


def reset_schedule(pk, user, *, revision, reason):
    with team_locked(pk, revision=revision) as (t, _):
        if t.rounds.exists():
            conflict('已经开场的赛程不能撤回。', 'team_plan_locked')
        plans = list(plan_query(t))
        before = [plan_snapshot(p) for p in plans]
        for p in plans:
            p.status, p.version = 'voided', p.version + 1
        TeamMatchPlan.objects.bulk_update(plans, ['status', 'version'])
        audit(t, user, 'schedule_withdrawn', {'plans': before}, {'schedule_revision': t.team_settings.schedule_revision}, reason)


def current_plan(t, match_id):
    return get_object_or_404(plan_query(t), pk=match_id)


def check_plan_version(p, version):
    if p.version != version:
        conflict('出场计划已被更新，请载入最新名单。', 'stale_team_plan')
    if p.table_id or p.status == 'started':
        conflict('已开场的队伍、人员和位置不能修改。', 'team_plan_locked')


def valid_member(t, team_id, member_id):
    member = TeamMember.objects.filter(pk=member_id, active=True, team_id=team_id, team__tournament=t, team__active=True).select_related('participant').first()
    if member is None:
        raise ValidationError({'lineup': ['出场成员须属于本赛的对应队伍。']})
    return member


def lineup_members(t, p):
    if len(p.team_ids) != 4 or len(set(p.team_ids)) != 4 or set(p.lineup) != {str(pk) for pk in p.team_ids}:
        raise ValidationError({'lineup': ['每场须由四支不同队伍各指定一名成员。']})
    result = []
    for team_id in p.team_ids:
        member_id = p.lineup[str(team_id)]
        if type(member_id) is not int:
            raise ValidationError({'lineup': ['出场名单尚未填齐。']})
        member = valid_member(t, team_id, member_id)
        if p.stage_id:
            rep = get_object_or_404(TeamStageRepresentative, stage=p.stage, team_id=team_id)
            if rep.member_id != member.pk:
                raise ValidationError({'lineup': ['同周期同位置须由同一名成员完成全部场次。']})
        result.append(member)
    if len({m.participant_id for m in result}) != 4:
        raise ValidationError({'lineup': ['同一场不能重复安排选手。']})
    return result


def update_plan(pk, match_id, user, *, version, lineup=None, team_ids=None, captain_supplied=False):
    with team_locked(pk) as (t, _):
        p = current_plan(t, match_id)
        check_plan_version(p, version)
        if p.status != 'draft':
            conflict('请先撤回已确认计划，再编辑名单。', 'team_plan_confirmed')
        before = plan_snapshot(p)
        if team_ids is not None:
            if t.pairing_strategy != TEAM_MANUAL:
                raise ValidationError({'team_ids': ['均衡随机模式不接受手动四队覆盖。']})
            allowed = set(t.teams.filter(active=True).values_list('pk', flat=True))
            if len(team_ids) != 4 or len(set(team_ids)) != 4 or not set(team_ids) <= allowed:
                raise ValidationError({'team_ids': ['每场需要本赛四支不同队伍。']})
            p.team_ids = team_ids
            p.lineup = {str(team_id): p.lineup.get(str(team_id)) for team_id in team_ids}
            if p.stage_id:
                p.lineup = {str(team_id): get_object_or_404(TeamStageRepresentative, stage=p.stage, team_id=team_id).member_id for team_id in team_ids}
        if lineup is not None:
            if p.stage_id:
                raise ValidationError({'lineup': ['固定位置模式请编辑本位置的队伍代表。']})
            seen = set()
            for item in lineup:
                team_id, member_id = item['team_id'], item['member_id']
                if team_id in seen or team_id not in p.team_ids:
                    raise ValidationError({'lineup': ['队伍重复或不属于本场。']})
                seen.add(team_id)
                if member_id is not None:
                    valid_member(t, team_id, member_id)
                p.lineup[str(team_id)] = member_id
        if p.stage_id:
            p.captain_supplied = all(row.captain_supplied for row in p.stage.representatives.filter(team_id__in=p.team_ids))
        else:
            p.captain_supplied = captain_supplied
        p.version += 1
        p.save()
        audit(t, user, 'plan_updated', before, plan_snapshot(p))
        return plan_data(p, roster(t))


def set_representative(pk, stage_id, user, *, team_id, member_id, revision, captain_supplied=False, withdraw_confirmed=False, reason=''):
    with team_locked(pk, revision=revision) as (t, _):
        stage = get_object_or_404(TeamStage, pk=stage_id, tournament=t, schedule_revision=t.team_settings.schedule_revision)
        if not plan_query(t).filter(stage=stage).exists():
            conflict('此位置属于已撤回赛程，代表与来源只保留为历史。', 'team_stage_inactive')
        rep = get_object_or_404(TeamStageRepresentative, stage=stage, team_id=team_id)
        member = valid_member(t, team_id, member_id) if member_id is not None else None
        captain_supplied = bool(member is not None and captain_supplied)
        changed = rep.member_id != member_id or rep.captain_supplied != captain_supplied
        if rep.locked and changed:
            conflict('该位置已开场，本周期由原代表打满配置场数。', 'stage_representative_locked')
        affected = [p for p in plan_query(t).filter(stage=stage, table__isnull=True) if team_id in p.team_ids]
        if changed and any(p.status == 'confirmed' for p in affected) and (not withdraw_confirmed or not reason.strip()):
            conflict('更换代表须明确撤回本队在该位置已确认的计划并填写原因。', 'team_plan_confirmed')
        before = {'stage_id': stage.pk, 'team_id': team_id, 'member_id': rep.member_id,
                  'captain_supplied': rep.captain_supplied, 'plans': [plan_snapshot(p) for p in affected]}
        rep.member, rep.captain_supplied = member, captain_supplied
        rep.save(update_fields=['member', 'captain_supplied'])
        supplied = {row.team_id: row.captain_supplied for row in stage.representatives.all()}
        for p in affected:
            if changed and p.status == 'confirmed':
                p.status, p.confirmed_by, p.confirmed_at = 'draft', None, None
            all_supplied = all(supplied.get(pk, False) for pk in p.team_ids)
            if p.lineup.get(str(team_id)) != member_id or p.captain_supplied != all_supplied:
                p.lineup[str(team_id)] = member_id
                p.captain_supplied = all_supplied
                p.version += 1
                p.save()
        audit(t, user, 'representative_updated', before, {'stage_id': stage.pk, 'team_id': team_id, 'member_id': member_id,
              'captain_supplied': captain_supplied, 'plans': [plan_snapshot(p) for p in affected]}, reason)


def confirm_plans(pk, user, sources):
    with team_locked(pk) as (t, _):
        validate_schedule(t)
        ids = [row['match_id'] for row in sources]
        if not ids or len(ids) != len(set(ids)):
            raise ValidationError({'plan_sources': ['请选择不重复的待确认比赛。']})
        plans = list(plan_query(t).filter(pk__in=ids))
        if len(plans) != len(ids):
            raise ValidationError({'plan_sources': ['计划不属于当前赛程。']})
        versions = {row['match_id']: row['version'] for row in sources}
        before = [plan_snapshot(p) for p in plans]
        for p in plans:
            check_plan_version(p, versions[p.pk])
            if p.status != 'draft':
                conflict('出场计划已经确认，请刷新。', 'team_plan_confirmed')
            lineup_members(t, p)
            if p.stage_id and not all(row.captain_supplied for row in p.stage.representatives.filter(team_id__in=p.team_ids)):
                raise ValidationError({'captain_supplied': ['本位置每支参赛队伍的代表须分别确认来源。']})
            if not p.captain_supplied:
                raise ValidationError({'captain_supplied': ['请先标明已收到队长指定名单。']})
            p.status, p.confirmed_by, p.confirmed_at, p.version = 'confirmed', user, timezone.now(), p.version + 1
        TeamMatchPlan.objects.bulk_update(plans, ['status', 'confirmed_by', 'confirmed_at', 'version'])
        audit(t, user, 'plans_confirmed', {'plans': before}, {'plans': [plan_snapshot(p) for p in plans]})


def set_representatives(pk, stage_id, user, *, revision, representatives, captain_supplied=False, withdraw_confirmed=False, reason=''):
    with team_locked(pk, revision=revision) as (t, _):
        ids = [row['team_id'] for row in representatives]
        if not representatives or len(ids) != len(set(ids)):
            raise ValidationError({'representatives': ['请选择不重复的队伍代表。']})
        for row in representatives:
            set_representative(pk, stage_id, user, revision=t.revision, team_id=row['team_id'], member_id=row['member_id'],
                               captain_supplied=captain_supplied, withdraw_confirmed=withdraw_confirmed, reason=reason)
            t.refresh_from_db()
        return {'revision': t.revision}


def withdraw_plan(pk, match_id, user, *, version, reason):
    with team_locked(pk) as (t, _):
        p = current_plan(t, match_id)
        check_plan_version(p, version)
        if p.status != 'confirmed':
            conflict('仅未开场且已确认的计划可以撤回。', 'team_plan_not_confirmed')
        before = plan_snapshot(p)
        p.status, p.confirmed_by, p.confirmed_at, p.version = 'draft', None, None, p.version + 1
        p.save()
        audit(t, user, 'plan_withdrawn', before, plan_snapshot(p), reason)


def result_batch(t):
    from .competition_services import confirmed_result_rows
    return confirmed_result_rows(t)


def preview_team_changes(t, table, scores, results):
    teams = roster(t)
    by_participant = {member['participant_id']: team for team in teams for member in team['members']}
    totals = {team['id']: Fraction() for team in teams}
    previous = {}
    for result in results:
        for item in result.scores:
            team = by_participant.get(item['participant_id'])
            if team is None:
                raise ValidationError({'scores': ['成绩选手不属于冻结团队阵容。']})
            totals[team['id']] += unpack(item['score'])
            if result.table_id == table.pk:
                previous[item['participant_id']] = unpack(item['score'])
    changes = []
    for item in scores:
        team = by_participant[item['participant_id']]
        old = previous.get(item['participant_id'], Fraction())
        change = unpack(item['score']) - old if item['score'] is not None else None
        changes.append({'participant_id': item['participant_id'], 'team_id': team['id'], 'team_name': team['name'],
                        'confirmed_total': pack(totals[team['id']]), 'previous_score': pack(old),
                        'score_change': pack(change) if change is not None else None,
                        'projected_total': pack(totals[team['id']] + change) if change is not None else None})
    return changes


def current_stage(plans, results):
    done = {row.table_id for row in results}
    pending = [p for p in plans if p.table_id not in done]
    return pending[0].stage_id if pending else None


def next_plans(t, plans, results, tables):
    if t.status != 'started':
        conflict('请先启动团队赛。', 'tournament_not_started')
    latest = t.rounds.order_by('-round_number').first()
    if latest:
        validate_batch(latest)
        done = {r.table_id for r in results}
        if set(latest.tables.values_list('pk', flat=True)) - done:
            conflict('当前时段成绩尚未全部确认。', 'results_incomplete')
    stage_id = current_stage(plans, results)
    pending = [p for p in plans if p.table_id is None and (stage_id is None or p.stage_id == stage_id)]
    if not pending:
        conflict('没有待开场的比赛，请检查成绩或完赛。', 'team_no_next_match')
    selected, occupied = [], set()
    for p in pending:
        if p.status != 'confirmed':
            if not selected:
                conflict('下一场名单尚未确认，请先收齐队长名单。', 'team_plan_not_confirmed')
            break
        members = lineup_members(t, p)
        ids = {m.participant_id for m in members}
        if ids & occupied:
            break
        selected.append((p, members)); occupied.update(ids)
        if len(selected) == tables:
            break
    return selected


def preview_batch(pk, user, machine_ids=None):
    from .competition_services import source_versions, mapping
    t = get_object_or_404(Tournament, pk=pk)
    require_team(t)
    if t.fixed_tables.exists():
        if machine_ids is not None:
            raise ValidationError({'machine_ids': ['后续时段沿用本赛固定物理桌。']})
        count = t.fixed_tables.count()
        mapped = mapping(t)
    else:
        if not machine_ids or not 1 <= len(machine_ids) <= 4 or len(set(machine_ids)) != len(machine_ids):
            raise ValidationError({'machine_ids': ['请选择1～4张不同的可用物理桌。']})
        machines = list(MahjongMachine.objects.filter(pk__in=machine_ids, status='available'))
        if len(machines) != len(machine_ids):
            conflict('所选物理桌不可用，请刷新。', 'machine_unavailable')
        by_id = {m.pk: m for m in machines}
        mapped = [{'ordinal': i + 1, 'machine_id': pk, 'machine_no': by_id[pk].machine_no, 'name': by_id[pk].name} for i, pk in enumerate(machine_ids)]
        count = len(mapped)
    plans = list(plan_query(t))
    validate_schedule(t, plans)
    results = result_batch(t)
    selected = next_plans(t, plans, results, count)
    teams = roster(t)
    payload = {'tournament_id': t.pk, 'user_id': user.pk, 'revision': t.revision,
               'schedule_revision': t.team_settings.schedule_revision, 'plans': plan_sources([p for p, _ in selected]),
               'source_versions': source_versions(t, results=results), 'roster': roster_source(t), 'machine_ids': machine_ids, 'rules': rules(t)}
    return {'batch_number': (t.rounds.order_by('-round_number').first().round_number + 1) if t.rounds.exists() else 1,
            'tables': [{'ordinal': index + 1, 'mapping': mapped[index], 'match': plan_data(p, teams)} for index, (p, _) in enumerate(selected)],
            'token': signing.dumps(payload, salt=SALT_BATCH, compress=True)}


def start_batch(pk, user, token):
    from .competition_services import source_versions, check_mapping
    with team_locked(pk, status='started') as (t, machines):
        payload = load_token(token, SALT_BATCH)
        if (payload.get('tournament_id'), payload.get('user_id')) != (t.pk, user.pk):
            raise ValidationError({'token': ['开场预览不属于本赛事或管理员。']})
        plans = list(plan_query(t)); results = result_batch(t)
        if payload.get('revision') != t.revision - 1 or payload.get('schedule_revision') != t.team_settings.schedule_revision or payload.get('source_versions') != source_versions(t, results=results) or payload.get('roster') != roster_source(t) or payload.get('rules') != rules(t):
            conflict('赛程、名单或成绩已变化，请重新预览开场。', 'stale_team_preview')
        ids = payload.get('machine_ids')
        if not t.fixed_tables.exists():
            if not ids or len(ids) != len(set(ids)) or not 1 <= len(ids) <= 4:
                raise ValidationError({'machine_ids': ['必须明确选择固定物理桌。']})
            for index, machine_id in enumerate(ids):
                machine = machines.get(machine_id)
                if machine is None or machine.status != 'available':
                    conflict('固定物理桌不可用。', 'machine_unavailable')
                fixed = TournamentTable.objects.create(tournament=t, ordinal=index + 1)
                Reservation.objects.create(table=fixed, machine=machine, machine_no_snapshot=machine.machine_no, created_by=user)
            t.resource_state = 'fixed'; t.save(update_fields=['resource_state'])
        selected = next_plans(t, plans, results, t.fixed_tables.count())
        if payload.get('plans') != plan_sources([p for p, _ in selected]):
            conflict('当前待开场计划已变化，请重新预览。', 'stale_team_preview')
        fixed = check_mapping(t, participant_count=len(selected) * 4)
        latest = t.rounds.order_by('-round_number').first()
        batch = TournamentRound.objects.create(tournament=t, competition_type='team', round_number=latest.round_number + 1 if latest else 1,
            generated_by=user, generation_snapshot={'team_plan_sources': payload['plans'], 'roster_snapshot': payload['roster'],
                'source_versions': payload['source_versions'], 'rules': rules(t), 'schedule_revision': t.team_settings.schedule_revision})
        for index, (p, members) in enumerate(selected):
            reservation = fixed[index].reservations.get(status='active')
            table = RoundTable.objects.create(round=batch, table_number=index + 1, tournament_table=fixed[index],
                bonus_source='team_zero_v1', machine_snapshot={'machine_id': reservation.machine_id, 'machine_no': reservation.machine_no_snapshot, 'reservation_id': reservation.pk})
            random.SystemRandom().shuffle(members)
            RoundSeat.objects.bulk_create([RoundSeat(round=batch, table=table, participant=m.participant, seat_wind=wind)
                                          for m, wind in zip(members, RoundSeat.Wind.values)])
            p.table, p.status, p.version = table, 'started', p.version + 1
            p.save()
            if p.stage_id:
                TeamStageRepresentative.objects.filter(stage=p.stage, team_id__in=p.team_ids).update(locked=True)
        validate_batch(batch)
        audit(t, user, 'batch_started', {'preview_plans': payload['plans']}, {'batch_id': batch.pk, 'batch_number': batch.round_number,
              'plans': [plan_snapshot(p) for p, _ in selected]})
        return batch


def validate_batch(batch):
    t = batch.tournament
    require_team(t)
    if batch.competition_type != 'team' or t.status not in ('started', 'completed'):
        raise ValidationError({'batch': ['团队时段与赛事状态不一致。']})
    tables = list(batch.tables.all())
    if not 1 <= len(tables) <= 4 or [table.table_number for table in tables] != list(range(1, len(tables) + 1)):
        raise ValidationError({'tables': ['每个时段使用1～4张有序逻辑桌。']})
    seen = set()
    for table in tables:
        p = get_object_or_404(TeamMatchPlan, tournament=t, table=table, status='started', schedule_revision=t.team_settings.schedule_revision)
        members = lineup_members(t, p)
        expected = {m.participant_id for m in members}
        seats = list(table.seats.select_related('participant', 'table', 'round'))
        if len(seats) != 4 or {s.participant_id for s in seats} != expected or {s.seat_wind for s in seats} != set(RoundSeat.Wind.values) or expected & seen:
            raise ValidationError({'lineup': ['实际座次必须覆盖计划四人，且同一时段选手不能重叠。']})
        if table.tournament_table is None or table.tournament_table.tournament_id != t.pk:
            raise ValidationError({'tables': ['逻辑桌必须属于本赛事。']})
        for seat in seats:
            try:
                seat.clean()
            except ModelValidationError as error:
                raise ValidationError(error.message_dict) from None
            if seat.round_id != batch.pk:
                raise ValidationError({'seats': ['座次必须属于当前时段。']})
        seen.update(expected)


def rankings(t, results, teams, plans):
    from .competition_services import source_versions, metric
    from .performance_stats import add_statistics
    people, by_participant = {}, {}
    for team in teams:
        for member in team['members']:
            pid = member['participant_id']
            by_participant[pid] = team['id']
            people[pid] = {'participant_id': pid, 'display_name': member['display_name'], 'team_id': team['id'], 'team_name': team['name'],
                           'total': pack(0), 'rounds': [], 'first_count': 0, 'second_count': 0, 'confirmed_rounds': 0, 'eliminated_after_round': None}
    rows = {team['id']: {'team_id': team['id'], 'name': team['name'], 'total': pack(0), 'first_count': 0, 'second_count': 0,
                        'confirmed_matches': 0, 'planned_matches': sum(team['id'] in p.team_ids for p in plans), 'matches': []} for team in teams}
    match_by_table = {p.table_id: p for p in plans if p.table_id}
    for result in results:
        p = match_by_table.get(result.table_id)
        if p is None:
            raise ValidationError({'scores': ['确认成绩没有对应团队计划。']})
        for item in result.scores:
            pid = item['participant_id']
            if pid not in by_participant:
                raise ValidationError({'scores': ['成绩选手不属于冻结团队阵容。']})
            person, team = people[pid], rows[by_participant[pid]]
            detail = {**item, 'match_number': p.match_number, 'match_id': p.pk, 'round_number': result.table.round.round_number,
                      'table_number': result.table.table_number, 'cycle': p.stage.cycle if p.stage_id else None,
                      'position_label': p.stage.position_label if p.stage_id else '', 'table_id': result.table_id}
            person['rounds'].append(detail)
            person['total'] = pack(unpack(person['total']) + unpack(item['score']))
            person['first_count'] += item['rank'] == 1; person['second_count'] += item['rank'] == 2
            person['confirmed_rounds'] += 1
            team['total'] = pack(unpack(team['total']) + unpack(item['score']))
            team['first_count'] += item['rank'] == 1; team['second_count'] += item['rank'] == 2
            team['confirmed_matches'] += 1
            team['matches'].append({**detail, 'display_name': person['display_name']})
    ordered = sorted(rows.values(), key=lambda row: (unpack(row['total']), row['first_count'], row['second_count']), reverse=True)
    groups, position = [], 1
    versions, source, sources = source_versions(t, results=results), source_from_roster(teams), plan_sources(plans)
    lotteries = [row for row in t.lotteries.filter(entity_type='team', purpose='final', confirmed_at__isnull=False).order_by('-id')
                 if row.source_versions == versions and row.roster_snapshot == source and row.plan_sources == sources]
    for _, group in groupby(ordered, lambda row: (unpack(row['total']), row['first_count'], row['second_count'])):
        values = list(group); ids = {row['team_id'] for row in values}
        lottery = next((draw for draw in lotteries if set(draw.members) == ids), None) if len(values) > 1 else None
        if lottery:
            index = {pk: i for i, pk in enumerate(lottery.order)}
            values.sort(key=lambda row: index[row['team_id']])
        elif len(values) > 1:
            groups.append([row['team_id'] for row in values])
        for i, row in enumerate(values):
            row['rank'] = position + i if lottery or len(values) == 1 else position
            row['lottery_id'] = lottery.pk if lottery else None
            row['contributions'] = [people[m['participant_id']] for team in teams if team['id'] == row['team_id'] for m in team['members']]
        ordered[position - 1:position - 1 + len(values)] = values
        position += len(values)
    auxiliary = sorted((p for p in people.values() if p['confirmed_rounds']), key=metric, reverse=True)
    rank, previous = 0, None
    for i, person in enumerate(auxiliary, 1):
        key = metric(person)
        if key != previous:
            rank, previous = i, key
        person['rank'] = rank
    for person in people.values():
        if not person['confirmed_rounds']:
            person['rank'] = None
            auxiliary.append(person)
    statistics = add_statistics(auxiliary)
    return ordered, groups, auxiliary, statistics


def ready_team_final(t, plans, results):
    try:
        validate_schedule(t, plans)
    except (TournamentConflict, ValidationError):
        return False
    done = {row.table_id for row in results}
    return bool(plans) and all(p.status == 'started' and p.table_id in done for p in plans)


def team_data(t):
    require_team(t)
    teams = roster(t)
    return {**{key: getattr(t, key) for key in ['id', 'name', 'description', 'competition_type', 'round_count', 'starting_points', 'return_points',
             'uma', 'oka_override', 'pairing_strategy', 'status', 'created_by_id', 'created_at', 'updated_at', 'started_at', 'revision',
             'resource_state', 'completed_at', 'champion_id', 'champion_team_id', 'score_tie_policy', 'champion_tiebreak_policy', 'rules_version', 'rules_source']},
            'created_by': t.created_by_id, 'round_count': None, 'oka': t.oka, 'table_bonus_policy': 'none', 'ranked_table_bonuses': ['0'] * 4,
            'participant_count': sum(len(team['members']) for team in teams), 'expected_table_count': None,
            'participants': [{'id': m['participant_id'], 'player_id': m['player_id'], 'display_name': m['display_name'],
                              'display_name_snapshot': m['display_name'] if t.status != 'draft' else '', 'is_active': m['is_active'], 'team_id': team['id']}
                             for team in teams for m in team['members']], 'teams': teams, 'team_settings': config_data(t.team_settings)}


def workspace(t):
    from .competition_services import source_versions, mapping, result_data
    require_team(t)
    if t.status == 'completed':
        return {**deepcopy(t.final_snapshot), 'status': 'completed', 'competition_type': 'team',
                'revision': t.revision, 'mapping': mapping(t), 'resource_state': t.resource_state,
                'lotteries': [team_lottery_data(row) for row in t.lotteries.filter(entity_type='team')],
                'stages': [], 'current_stage_id': None, 'unresolved_groups': [],
                'ready': False, 'all_results_confirmed': True}
    results, plans, teams = result_batch(t), list(plan_query(t)), roster(t)
    rows, groups, auxiliary, statistics = rankings(t, results, teams, plans)
    done = {row.table_id: row for row in results}
    ready = ready_team_final(t, plans, results)
    latest = t.rounds.order_by('-round_number').first()
    stages = []
    for stage in t.team_stages.filter(schedule_revision=t.team_settings.schedule_revision).prefetch_related('representatives'):
        games = [p for p in plans if p.stage_id == stage.pk]
        if not games:
            continue
        stages.append({'id': stage.pk, 'stage_number': stage.stage_number, 'cycle': stage.cycle, 'position_label': stage.position_label,
                       'games_per_team': stage.games_per_team, 'match_count': len(games), 'confirmed_matches': sum(p.table_id in done for p in games),
                       'representatives': [{'team_id': r.team_id, 'member_id': r.member_id, 'locked': r.locked,
                           'captain_supplied': r.captain_supplied,
                           'confirmed_matches': sum(r.team_id in p.team_ids and p.table_id in done for p in games),
                           'planned_matches': sum(r.team_id in p.team_ids for p in games)} for r in stage.representatives.all()]})
    return {'status': t.status, 'competition_type': 'team', 'revision': t.revision, 'teams': teams, 'team_settings': config_data(t.team_settings),
            'team_standings': rows, 'standings': auxiliary, 'statistics': statistics, 'unresolved_groups': groups if ready else [],
            'ready': ready and not groups, 'all_results_confirmed': ready, 'source_versions': source_versions(t, results=results),
            'roster_snapshot': source_from_roster(teams), 'plan_sources': plan_sources(plans), 'stages': stages,
            'current_stage_id': current_stage(plans, results), 'match_count': len(plans), 'completed_matches': len(done),
            'latest_batch_number': latest.round_number if latest else None, 'mapping': mapping(t), 'resource_state': t.resource_state,
            'rules': rules(t), 'lotteries': [team_lottery_data(row) for row in t.lotteries.filter(entity_type='team')], 'completed_at': None}


def team_lottery_data(row):
    return {key: getattr(row, key) for key in ('id', 'entity_type', 'members', 'order', 'method', 'description', 'drawn_at',
        'created_by_id', 'created_at', 'confirmed_by_id', 'confirmed_at', 'voided_by_id', 'voided_at', 'void_reason',
        'source_versions', 'roster_snapshot', 'plan_sources')}


def check_sources(t, values, results, plans, teams):
    from .competition_services import source_versions
    if values.get('source_versions') != source_versions(t, results=results) or values.get('roster_snapshot') != roster_source(t, teams=teams) or values.get('plan_sources') != plan_sources(plans):
        conflict('成绩、阵容或出场计划来源已变化，请刷新团队榜。', 'stale_standings')


def record_team_lottery(pk, user, values):
    with team_locked(pk, status='started') as (t, _):
        results, plans, team_objects = result_batch(t), list(plan_query(t)), active_teams(t)
        teams = roster(t, teams=team_objects)
        if not ready_team_final(t, plans, results):
            conflict('全部计划成绩确认后才能记录最终团队抽签。', 'results_incomplete')
        check_sources(t, values, results, plans, team_objects)
        _, groups, _, _ = rankings(t, results, teams, plans)
        members, order = values['members'], values['order']
        if values.get('entity_type') != 'team' or len(members) != len(set(members)) or set(members) not in [set(g) for g in groups] or len(order) != len(members) or set(order) != set(members):
            raise ValidationError({'members': ['团队抽签须完整覆盖一个待决团队组。']})
        for draw in t.lotteries.filter(entity_type='team', confirmed_at__isnull=True, voided_at__isnull=True):
            if set(draw.members) == set(members) and draw.source_versions == values['source_versions'] and draw.roster_snapshot == values['roster_snapshot'] and draw.plan_sources == values['plan_sources']:
                conflict('该团队组已有待确认抽签，请先确认或填写原因作废。', 'lottery_pending')
        return LotteryRecord.objects.create(tournament=t, created_by=user, entity_type='team', purpose='final', rules_version=t.rules_version,
            source_versions=values['source_versions'], roster_snapshot=roster_source(t, teams=team_objects), plan_sources=plan_sources(plans),
            members=members, order=order, method=values['method'], description=values['description'], drawn_at=values['drawn_at'])


def confirm_team_lottery(pk, lottery_id, user):
    with team_locked(pk, status='started') as (t, _):
        row = get_object_or_404(LotteryRecord, pk=lottery_id, tournament=t, entity_type='team')
        if row.voided_at:
            conflict('团队抽签记录已作废。', 'lottery_voided')
        results, plans, team_objects = result_batch(t), list(plan_query(t)), active_teams(t)
        if not ready_team_final(t, plans, results):
            conflict('团队成绩还未全部确认。', 'results_incomplete')
        check_sources(t, {'source_versions': row.source_versions, 'roster_snapshot': row.roster_snapshot, 'plan_sources': row.plan_sources}, results, plans, team_objects)
        _, groups, _, _ = rankings(t, results, roster(t, teams=team_objects), plans)
        if row.confirmed_at or set(row.members) not in [set(g) for g in groups]:
            conflict('团队抽签已确认或并列组已变化。', 'lottery_conflict')
        row.confirmed_by, row.confirmed_at = user, timezone.now()
        row.save(update_fields=['confirmed_by', 'confirmed_at'])
        return row


def finish_team(pk, user, values):
    from .competition_services import release_reservation, source_versions
    with team_locked(pk, status='started') as (t, _):
        results, plans, team_objects = result_batch(t), list(plan_query(t)), active_teams(t)
        if not ready_team_final(t, plans, results):
            conflict('团队赛尚有未开场计划或未确认成绩。', 'results_incomplete')
        check_sources(t, values, results, plans, team_objects)
        teams = roster(t, teams=team_objects)
        rows, groups, auxiliary, statistics = rankings(t, results, teams, plans)
        if groups:
            conflict('团队完全并列组仍需公开抽签并二次确认。', 'lottery_required')
        if not rows or rows[0]['rank'] != 1 or sum(row['rank'] == 1 for row in rows) != 1:
            conflict('尚未确定唯一团队冠军。', 'champion_unresolved')
        t.status, t.completed_by, t.completed_at, t.champion_team_id = 'completed', user, timezone.now(), rows[0]['team_id']
        t.final_snapshot = {'competition_type': 'team', 'status': 'completed', 'team_standings': rows, 'standings': auxiliary,
            'statistics': statistics, 'champion_team_id': t.champion_team_id, 'champion_id': None, 'teams': teams,
            'team_settings': config_data(t.team_settings), 'rules': rules(t), 'source_versions': source_versions(t, results=results),
            'roster_snapshot': roster_source(t, teams=team_objects), 'plan_sources': plan_sources(plans),
            'lottery_ids': sorted({row['lottery_id'] for row in rows if row['lottery_id'] is not None}),
            'completed_by': user.pk, 'completed_at': t.completed_at.isoformat(), 'match_count': len(plans), 'completed_matches': len(plans)}
        t.save()
        for reservation in Reservation.objects.filter(table__tournament=t, status='active'):
            release_reservation(reservation, user, '团队赛正式完赛结束本场关联')
        audit(t, user, 'completed', {}, {'champion_team_id': t.champion_team_id, 'source_versions': t.final_snapshot['source_versions']})
        return workspace(t)
