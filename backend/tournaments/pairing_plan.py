"""Read-only signed previews bound to frozen roster and result versions."""
import random

from django.core import signing
from django.core.exceptions import ValidationError as ModelValidationError
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from .models import Tournament, RoundTable
from .pairing import LEGACY, RANDOM, RANKED, MANUAL, SWISS_REPEATS, SWISS_SCORES, CHOICES, encounters, repeated_pairs, swiss_groups, validate_groups
from .scoring import pack, unpack, rules

SALT = 'tournaments.pairing-plan.v1'
MAX_AGE = 1800


def meetings_for(tournament, number):
    tables = RoundTable.objects.filter(round__tournament=tournament, round__round_number__lt=number).prefetch_related('seats')
    return encounters([[seat.participant_id for seat in table.seats.all()] for table in tables])


def preview(tournament_id, user, number):
    from .competition_services import confirmed_result_rows, source_versions, participant_statuses, ranking, metric, require_round_confirmed, conflict
    t = get_object_or_404(Tournament, pk=tournament_id)
    if t.status != 'started':
        conflict('请先启动赛事，再预览本轮分桌。', 'tournament_not_started')
    if t.competition_type != 'individual':
        conflict('团队赛使用出场计划与开赛批次，请进入团队工作台。', 'competition_mode_mismatch')
    if t.pairing_strategy == LEGACY:
        raise ValidationError({'pairing_strategy': ['历史赛事沿用原分桌规则。']})
    latest = t.rounds.order_by('-round_number').first()
    if number != (latest.round_number + 1 if latest else 1) or number > t.round_count:
        conflict('只能预览尚未生成的下一轮。', 'round_not_next')
    entries = list(t.participants.all())
    participants = [p for p in entries if p.eliminated_after_round is None]
    ids = [p.pk for p in participants]
    if len(ids) not in (4, 8, 12, 16) or any(not p.display_name_snapshot for p in participants):
        raise ValidationError({'participants': ['冻结名单不完整。']})
    results = confirmed_result_rows(t)
    standings, _ = ranking(t, results=results, participants=entries, active_only=True)
    scores = {row['participant_id']: unpack(row['total']) for row in standings}
    if number == 1:
        random.SystemRandom().shuffle(ids)
        first_order = list(ids)
    else:
        require_round_confirmed(latest)
        first_order = t.first_round_order
        if set(first_order) != {p.pk for p in entries} or len(first_order) != len(entries):
            conflict('首轮随机序列不完整，需复核。', 'legacy_order_invalid')
        order = {pk: index for index, pk in enumerate(first_order)}
        standings.sort(key=lambda row: (metric(row), -order[row['participant_id']]), reverse=True)
        ids = [row['participant_id'] for row in standings]
        if t.pairing_strategy == RANDOM:
            random.SystemRandom().shuffle(ids)
    meetings = meetings_for(t, number)
    groups = [ids[index:index+4] for index in range(0, len(ids), 4)]
    if number > 1 and t.pairing_strategy in (SWISS_REPEATS, SWISS_SCORES):
        groups = swiss_groups(ids, scores, meetings, repeats_first=t.pairing_strategy == SWISS_REPEATS)
    bonuses = t.ranked_table_bonuses[:len(groups)] if number > 1 and t.pairing_strategy == RANKED else ['0'] * len(groups)
    payload = {'tournament_id': t.pk, 'user_id': user.pk, 'number': number, 'revision': t.revision,
               'source_versions': source_versions(t, results=results), 'participant_statuses': participant_statuses(t, participants=entries), 'strategy': t.pairing_strategy,
               'participant_ids': sorted(p.pk for p in participants), 'first_order': first_order,
               'groups': groups, 'rules': rules(t)}
    return {'round_number': number, 'strategy': t.pairing_strategy, 'strategy_label': dict(CHOICES)[t.pairing_strategy],
            'manual': t.pairing_strategy == MANUAL, 'token': signing.dumps(payload, salt=SALT, compress=True),
            'participants': [{'id': p.pk, 'display_name': p.display_name_snapshot, 'total': pack(scores[p.pk])} for p in participants],
            'tables': [{'ordinal': index+1, 'label': 'ABCD'[index], 'participant_ids': group, 'base_bonus': bonuses[index]} for index, group in enumerate(groups)],
            **repeated_pairs(groups, meetings)}


def load(t, user, number, token, manual_groups):
    from .competition_services import source_versions, participant_statuses, conflict
    try:
        payload = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.SignatureExpired:
        raise ValidationError({'pairing_token': ['分桌预览已过期，请重新预览。']}) from None
    except (signing.BadSignature, TypeError, ValueError):
        raise ValidationError({'pairing_token': ['分桌预览签名无效，请重新预览。']}) from None
    if not isinstance(payload, dict) or (payload.get('tournament_id'), payload.get('user_id'), payload.get('number'), payload.get('strategy')) != (t.pk, user.pk, number, t.pairing_strategy):
        raise ValidationError({'pairing_token': ['分桌预览不属于本赛事、本轮或当前管理员。']})
    if payload.get('revision') != t.revision-1 or payload.get('source_versions') != source_versions(t) or payload.get('rules') != rules(t):
        conflict('赛事或成绩已变化，请重新预览分桌。', 'stale_pairing')
    entries = list(t.participants.all())
    if payload.get('participant_statuses') != participant_statuses(t, participants=entries):
        conflict('淘汰状态已变化，请重新预览分桌。', 'stale_pairing')
    expected = {p.pk for p in entries if p.eliminated_after_round is None}
    if set(payload.get('participant_ids', [])) != expected:
        conflict('冻结名单已变化，请重新预览。', 'stale_pairing')
    if t.pairing_strategy == MANUAL:
        if manual_groups is None:
            raise ValidationError({'participant_groups': ['请提交已确认的手动分桌名单。']})
        groups = manual_groups
    else:
        if manual_groups is not None:
            raise ValidationError({'participant_groups': ['自动策略不接受手动覆盖，请在新赛事中选择手动模式。']})
        groups = payload.get('groups')
    try:
        validate_groups(groups, expected)
    except ModelValidationError as error:
        raise ValidationError({'participant_groups': error.messages}) from None
    first_order = payload.get('first_order', [])
    if len(first_order) != len(entries) or set(first_order) != {p.pk for p in entries}:
        raise ValidationError({'pairing_token': ['首轮随机序列无效。']})
    return groups, first_order
