"""Complete tournament workflow. Lock order: machine pool -> tournament -> children.

All mutations share this order, including results, so SQLite obtains a write
reservation before reads. No transaction retries an uncertain write.
"""
import random
from contextlib import contextmanager
from copy import deepcopy
from fractions import Fraction
from itertools import groupby

from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from machines.locking import lock_machine_pool
from .models import (Tournament, TournamentRound, RoundTable, RoundSeat, MachineAllocation,
                     TournamentTable, TournamentMachineReservation as Reservation, TableResult, TableResultCorrection, LotteryRecord)
from .services import TournamentConflict, database_busy
from .scoring import pack, unpack, score, rules

WINDS = list(RoundSeat.Wind.values)


def conflict(message, code):
    raise TournamentConflict(message, code)


@contextmanager
def locked(pk, *, writable=True):
    try:
        with transaction.atomic():
            machines = {m.pk: m for m in lock_machine_pool()}
            Tournament.objects.filter(pk=pk).update(revision=F('revision') + 1)
            tournament = get_object_or_404(Tournament, pk=pk)
            if writable and tournament.status != 'started':
                conflict('赛事必须已启动且尚未完赛。', 'tournament_not_started')
            yield tournament, machines
    except OperationalError as exc:
        database_busy(exc)
    except IntegrityError:
        conflict('并发写入或数据约束冲突，操作已整体回滚，请刷新。', 'competition_conflict')


def occupied_ids():
    return set(Reservation.objects.filter(status='active').values_list('machine_id', flat=True)) | set(MachineAllocation.objects.filter(status='active').values_list('machine_id', flat=True))


def structure(round):
    from .round_services import validate_round_structure
    validate_round_structure(round)


def confirmed_result_rows(t):
    return list(TableResult.objects.filter(table__round__tournament=t, status='confirmed').select_related('table__round').order_by('table__round__round_number', 'table__table_number'))


def source_versions(t, *, results=None):
    if results is not None:
        return [{'table_id': row.table_id, 'version': row.version} for row in results]
    return list(TableResult.objects.filter(table__round__tournament=t, status='confirmed').order_by('table__round__round_number', 'table__table_number').values('table_id', 'version'))


def bridge_legacy(t, user):
    """Lazy safety net for legacy records; migration 0004 uses the same declared policy.

    Never rewrite old allocations/seats and never raise on malformed history:
    every existing table is bridged and even abnormal active reservations are
    mirrored to protect the pool, while resource_state requires explicit review.
    Only a complete first round (round 1, legal size, tables 1..n, four winds,
    exact participant cover) becomes the order source.
    """
    if t.resource_state != 'unselected' or not t.rounds.exists():
        return
    first = t.rounds.order_by('round_number').first()
    expected = set(t.participants.values_list('pk', flat=True))
    order = []
    tables = list(first.tables.order_by('table_number'))
    valid = first.round_number == 1 and len(expected) in (4, 8, 12, 16) and [x.table_number for x in tables] == list(range(1, len(expected)//4+1))
    for table in tables:
        seats = list(table.seats.all())
        by_wind = {s.seat_wind: s.participant_id for s in seats}
        if len(seats) == 4 and set(by_wind) == set(WINDS):
            order.extend(by_wind[w] for w in WINDS)
        else:
            valid = False
        fixed, _ = TournamentTable.objects.get_or_create(tournament=t, ordinal=table.table_number)
        # Existing allocation snapshot, not today's edited machine number.
        current = table.allocations.filter(status='active').select_related('machine').first()
        table.tournament_table = fixed
        original = table.allocations.order_by('id').first()
        table.machine_snapshot = {'machine_id': original.machine_id, 'machine_no': original.machine_no_snapshot, 'source': 'legacy_round_v1'} if original else {}
        table.save(update_fields=['tournament_table', 'machine_snapshot'])
        if current:
            Reservation.objects.get_or_create(legacy_allocation=current, defaults={'table': fixed, 'machine': current.machine, 'machine_no_snapshot': current.machine_no_snapshot, 'created_by_id': current.allocated_by_id, 'source': 'legacy_bridge_v1'})
        valid = valid and current is not None and current.machine.status == 'available'
    valid_order = len(order) == len(expected) == len(set(order)) and set(order) == expected
    t.first_round_order = order if valid_order else []
    t.order_source = 'legacy_table_wind_v1' if valid_order else 'legacy_incomplete'
    t.resource_state = 'fixed' if valid and valid_order else 'review_required'
    t.compatibility_audit = {'source': 'legacy_round_v1', 'identified_at': timezone.now().isoformat(), 'valid_allocations': bool(valid and valid_order)}
    t.save()


def mapping(t):
    rows = []
    for table in t.fixed_tables.all():
        active = table.reservations.filter(status='active').select_related('machine').first()
        history = []
        for r in table.reservations.select_related('machine'):
            history.append({'id': r.pk, 'machine_id': r.machine_id, 'machine_no': r.machine.machine_no, 'machine_no_snapshot': r.machine_no_snapshot, 'status': r.status, 'source': r.source, 'legacy_allocation_id': r.legacy_allocation_id, 'created_by': r.created_by_id, 'created_at': r.created_at, 'released_by': r.released_by_id, 'released_at': r.released_at, 'reason': r.reason, 'release_reason': r.release_reason})
        rows.append({'id': table.pk, 'ordinal': table.ordinal, 'label': 'ABCD'[table.ordinal - 1], 'reservation_id': active.pk if active else None, 'machine_id': active.machine_id if active else None, 'machine_no': active.machine.machine_no if active else None, 'name': active.machine.name if active else None, 'history': history})
    return rows


def check_mapping(t):
    rows = list(t.fixed_tables.all())
    if t.resource_state != 'fixed' or len(rows) != t.participants.count() // 4:
        conflict('请先完成物理桌兼容复核。', 'resource_review_required')
    for table in rows:
        active = table.reservations.filter(status='active').select_related('machine').first()
        if not active or active.machine.status != 'available':
            conflict('固定物理桌不可用，请故障替换后继续。', 'machine_unavailable')
        # Unbridged legacy writes must not bypass exclusivity.
        if MachineAllocation.objects.filter(machine=active.machine, status='active').exclude(pk=active.legacy_allocation_id).exists():
            conflict('存在旧分配占用冲突，需复核。', 'machine_occupied')
    return rows


def select_machines(t, machines, ids, user):
    if len(ids) != t.participants.count() // 4 or len(ids) != len(set(ids)):
        raise ValidationError({'machine_ids': ['选桌数量须为人数/4，且不得重复。']})
    occupied = occupied_ids()
    for pk in ids:
        if pk not in machines:
            conflict('设备池已变化，请刷新。', 'machine_unavailable')
        if machines[pk].status != 'available' or pk in occupied:
            conflict('所选物理桌不可用或已被占用。', 'machine_occupied')
    # IDs arrive in explicit preview A-D order; do not silently reorder.
    for ordinal, pk in enumerate(ids, 1):
        table, _ = TournamentTable.objects.get_or_create(tournament=t, ordinal=ordinal)
        Reservation.objects.create(table=table, machine=machines[pk], machine_no_snapshot=machines[pk].machine_no, created_by=user)
    t.resource_state = 'fixed'
    t.save(update_fields=['resource_state'])


def create_round(t, user, number, participants, *, rng=None):
    rng = rng or random.SystemRandom()
    fixed_tables = check_mapping(t)
    generated = TournamentRound.objects.create(tournament=t, round_number=number, generated_by=user, generation_snapshot={'source_versions': source_versions(t), 'first_round_order': t.first_round_order, 'rules': rules(t), 'sorted_participants': [p.pk for p in participants]})
    for index, fixed in enumerate(fixed_tables):
        active = fixed.reservations.get(status='active')
        table = RoundTable.objects.create(round=generated, table_number=fixed.ordinal, tournament_table=fixed, machine_snapshot={'machine_id': active.machine_id, 'machine_no': active.machine_no_snapshot, 'reservation_id': active.pk})
        group = participants[index*4:index*4+4]
        if number > 1:
            rng.shuffle(group)
        RoundSeat.objects.bulk_create([RoundSeat(round=generated, table=table, participant=p, seat_wind=w) for p, w in zip(group, WINDS, strict=True)])
    structure(generated)
    return generated


def generate(tournament_id, user, number, *, machine_ids=None, rng=None):
    with locked(tournament_id) as (t, machines):
        bridge_legacy(t, user)
        if t.rounds.filter(round_number=number).exists():
            conflict('此轮已生成，不能覆盖。', 'round_already_generated')
        latest = t.rounds.order_by('-round_number').first()
        expected = latest.round_number + 1 if latest else 1
        if number != expected or number > t.round_count:
            conflict('只能连续生成下一轮，且不得超过配置轮数。', 'round_not_next')
        participants = list(t.participants.all())
        if len(participants) not in (4, 8, 12, 16) or any(not p.display_name_snapshot for p in participants):
            raise ValidationError({'participants': ['冻结名单不完整。']})
        if number == 1:
            if machine_ids is None:
                raise ValidationError({'machine_ids': ['须明确选择并确认物理桌A～D。']})
            select_machines(t, machines, machine_ids, user)
            (rng or random.SystemRandom()).shuffle(participants)
            t.first_round_order = [p.pk for p in participants]
            t.order_source = 'persisted_shuffle_v1'
            t.save(update_fields=['first_round_order', 'order_source'])
        else:
            if machine_ids is not None:
                raise ValidationError({'machine_ids': ['换轮沿用固定物理桌，不能重新选桌。']})
            require_round_confirmed(latest)
            standings, _ = ranking(t)
            order = {pk: i for i, pk in enumerate(t.first_round_order)}
            if set(order) != {p.pk for p in participants}:
                conflict('首轮随机序列不完整，需复核。', 'legacy_order_invalid')
            standings.sort(key=lambda x: (metric(x), -order[x['participant_id']]), reverse=True)
            by_id = {p.pk: p for p in participants}
            participants = [by_id[x['participant_id']] for x in standings]
        return create_round(t, user, number, participants, rng=rng)


def require_round_confirmed(round):
    structure(round)
    if round.tables.filter(result__status='confirmed').count() != round.tables.count():
        conflict('本轮尚有未确认成绩。', 'results_incomplete')


def result_data(table):
    row = TableResult.objects.filter(table=table).first()
    return {'table_id': table.pk, 'version': row.version if row else 0, 'status': row.status if row else 'draft', 'points': row.points if row else {}, 'scores': row.scores if row else [], 'rules': row.rule_snapshot if row else {}, 'edited_by': row.edited_by_id if row else None, 'edited_at': row.edited_at if row else None, 'confirmed_by': row.confirmed_by_id if row else None, 'confirmed_at': row.confirmed_at if row else None, 'correction_count': row.corrections.count() if row else 0}


def parse_result_points(table, points):
    if not isinstance(points, list) or len(points) > 4:
        raise ValidationError({'points': ['点数最多包含本桌四名选手。']})
    allowed = set(table.seats.values_list('participant_id', flat=True))
    values = {}
    for item in points:
        if not isinstance(item, dict) or set(item) != {'participant_id', 'raw_points'}:
            raise ValidationError({'points': ['每项仅接受参赛选手和原始点数。']})
        participant, raw = item['participant_id'], item['raw_points']
        if type(participant) is not int or participant not in allowed or str(participant) in values:
            raise ValidationError({'points': ['重复选手或选手不属于本桌。']})
        if raw is not None and (type(raw) is not int or abs(raw) > 2**53 - 1):
            raise ValidationError({'points': ['点数必须是安全范围内的整数或空值。']})
        values[str(participant)] = raw
    return values


def validate_confirmed_points(t, table, values):
    allowed = {str(pk) for pk in table.seats.values_list('participant_id', flat=True)}
    if set(values) != allowed or len(allowed) != 4 or any(type(value) is not int for value in values.values()):
        raise ValidationError({'points': ['确认须完整填写本桌四名选手的整数点数。']})
    if sum(values.values()) != 4 * t.starting_points:
        raise ValidationError({'points': ['总点数必须等于四倍开局点数；异常可保存草稿。']})


def preview_result(table_id, version, points):
    """Read-only Fraction calculation, including incomplete/imbalanced input."""
    table = get_object_or_404(RoundTable.objects.select_related('round__tournament'), pk=table_id)
    t = table.round.tournament
    if t.status != 'started':
        conflict('仅进行中的赛事可以试算或更正成绩。', 'tournament_not_started')
    structure(table.round)
    row = TableResult.objects.filter(table=table).first()
    current_version = row.version if row else 0
    if version != current_version:
        conflict('成绩版本已变化，请载入最新成绩后核对。', 'stale_result')
    values = parse_result_points(table, points)
    snapshot = rules(t)
    complete = len(values) == 4 and all(value is not None for value in values.values())
    total = sum(value for value in values.values() if value is not None)
    scores = score(t, values) if complete else [
        {'participant_id': pk, 'raw_points': values.get(str(pk)), 'rank': None, 'tied': False,
         'base': pack(Fraction(values[str(pk)] - t.return_points, 1000)) if values.get(str(pk)) is not None else None,
         'bonus': None, 'score': None}
        for pk in table.seats.values_list('participant_id', flat=True)
    ]
    return {'table_id': table.pk, 'version': current_version, 'complete': complete,
            'valid_total': complete and total == 4 * t.starting_points,
            'total': str(total), 'expected_total': str(4 * t.starting_points),
            'difference': str(total - 4 * t.starting_points), 'scores': scores, 'rules': snapshot}


def result_snapshot(row):
    return deepcopy({'table_id': row.table_id, 'version': row.version, 'status': row.status,
                     'points': row.points, 'scores': row.scores, 'rules': row.rule_snapshot,
                     'edited_by': row.edited_by_id, 'edited_at': row.edited_at.isoformat() if row.edited_at else None,
                     'confirmed_by': row.confirmed_by_id, 'confirmed_at': row.confirmed_at.isoformat() if row.confirmed_at else None})


def correct_result(table_id, user, version, *, points, reason=''):
    table = get_object_or_404(RoundTable.objects.select_related('round'), pk=table_id)
    with locked(table.round.tournament_id) as (t, _):
        structure(table.round)
        row = get_object_or_404(TableResult, table=table)
        if row.status != 'confirmed':
            conflict('未确认成绩请使用草稿录入。', 'result_not_confirmed')
        if version != row.version:
            conflict('成绩版本已变化，请载入最新成绩后核对。', 'stale_result')
        if not isinstance(reason, str) or len(reason.strip()) > 500:
            raise ValidationError({'reason': ['更正说明最多500字符。']})
        values = parse_result_points(table, points)
        validate_confirmed_points(t, table, values)
        if values == row.points:
            return result_data(table)
        before = result_snapshot(row)
        row.points, row.scores, row.rule_snapshot = values, score(t, values), rules(t)
        row.version += 1
        row.edited_by, row.confirmed_by, row.confirmed_at = user, user, timezone.now()
        row.save()
        TableResultCorrection.objects.create(result=row, from_version=before['version'], to_version=row.version,
                                             before_snapshot=before, after_snapshot=result_snapshot(row),
                                             corrected_by=user, reason=reason.strip())
        # Ranking reads current confirmed scores. Existing rounds and lotteries
        # retain their original snapshots; obsolete lottery versions no longer rank.
        return result_data(table)


def result_corrections(table_id):
    table = get_object_or_404(RoundTable, pk=table_id)
    rows = TableResultCorrection.objects.filter(result__table=table).select_related('corrected_by')
    return {'table_id': table.pk, 'corrections': [
        {'id': row.pk, 'from_version': row.from_version, 'to_version': row.to_version,
         'before': row.before_snapshot, 'after': row.after_snapshot,
         'corrected_by': row.corrected_by_id, 'corrected_by_username': row.corrected_by.username,
         'corrected_at': row.corrected_at, 'reason': row.reason}
        for row in rows
    ]}


def write_result(table_id, user, version, *, points=None, confirm=False):
    table = get_object_or_404(RoundTable, pk=table_id)
    with locked(table.round.tournament_id) as (t, _):
        bridge_legacy(t, user)
        if t.resource_state == 'review_required':
            conflict('请先复核旧赛事资源。', 'resource_review_required')
        structure(table.round)
        row = TableResult.objects.filter(table=table).first()
        if row and row.status == 'confirmed':
            conflict('成绩已确认，请使用成绩更正入口。', 'result_locked')
        if version != (row.version if row else 0):
            conflict('成绩版本已变化，请刷新后核对。', 'stale_result')
        if row is None:
            row = TableResult(table=table, edited_by=user)
        else:
            row.version += 1
        if points is not None:
            row.points = parse_result_points(table, points)
            row.edited_by = user
        if confirm:
            validate_confirmed_points(t, table, row.points)
            row.scores = score(t, row.points)
            row.rule_snapshot = rules(t)
            row.status, row.confirmed_by, row.confirmed_at = 'confirmed', user, timezone.now()
        if points is None and row.pk:
            # Confirmation only: the draft editor and edited_at (auto_now) stay untouched.
            row.save(update_fields=['version', 'status', 'scores', 'rule_snapshot', 'confirmed_by', 'confirmed_at'])
        else:
            row.save()
        return result_data(table)


def metric(row):
    return (unpack(row['total']), row['first_count'], row['second_count'], *[unpack(r['score']) for r in reversed(row['rounds'])])


def ranking(t, *, results=None):
    results = confirmed_result_rows(t) if results is None else results
    entries = list(t.participants.all())
    rows = {p.pk: {'participant_id': p.pk, 'display_name': p.display_name_snapshot, 'rounds': [], 'first_count': 0, 'second_count': 0, 'total': pack(0), 'confirmed_rounds': 0} for p in entries}
    for result in results:
        for item in result.scores:
            row = rows[item['participant_id']]
            row['rounds'].append({**item, 'round_number': result.table.round.round_number, 'table_id': result.table_id})
            row['first_count'] += item['rank'] == 1
            row['second_count'] += item['rank'] == 2
            row['confirmed_rounds'] += 1
            row['total'] = pack(unpack(row['total']) + unpack(item['score']))
    ordered = sorted(rows.values(), key=metric, reverse=True)
    groups = []
    versions = source_versions(t, results=results)
    position = 1
    for _, values in groupby(ordered, metric):
        values = list(values)
        members = [r['participant_id'] for r in values]
        lottery = None
        if len(values) > 1:
            lottery = next((x for x in t.lotteries.filter(confirmed_at__isnull=False).order_by('-id') if x.source_versions == versions and set(x.members) == set(members)), None)
            if lottery:
                positions = {pk: i for i, pk in enumerate(lottery.order)}
                values.sort(key=lambda x: positions[x['participant_id']])
            else:
                groups.append(members)
        for index, row in enumerate(values):
            row['rank'] = position + index if lottery or len(values) == 1 else position
            row['lottery_id'] = lottery.pk if lottery else None
        ordered[position-1:position-1+len(values)] = values
        position += len(values)
    return ordered, groups


def ready_final(t, *, results=None):
    rounds = list(t.rounds.all())
    if [round.round_number for round in rounds] != list(range(1, t.round_count+1)):
        conflict('配置轮次尚未全部生成。', 'rounds_incomplete')
    if results is None:
        for round in rounds:
            require_round_confirmed(round)
    else:
        expected_tables = set()
        for round in rounds:
            structure(round)
            expected_tables.update(round.tables.values_list('pk', flat=True))
        if {result.table_id for result in results} != expected_tables:
            conflict('本轮尚有未确认成绩。', 'results_incomplete')


def preview(pk, *, tournament=None):
    t = tournament if tournament is not None else get_object_or_404(Tournament, pk=pk)
    if t.status == 'completed':
        return {'status': 'completed', **t.final_snapshot}
    results = confirmed_result_rows(t)
    rows, groups = ranking(t, results=results)
    ready = False
    try:
        ready_final(t, results=results)
        ready = t.resource_state in ('fixed', 'historical_only')
    except TournamentConflict:
        pass
    return {'status': t.status, 'standings': rows, 'unresolved_groups': groups if ready else [], 'ready': ready and not groups, 'all_results_confirmed': ready, 'source_versions': source_versions(t, results=results), 'rules': rules(t)}


def record_lottery(pk, user, values):
    with locked(pk) as (t, _):
        ready_final(t)
        _, groups = ranking(t)
        members = values['members']
        if len(members) != len(set(members)) or set(members) not in [set(g) for g in groups] or len(values['order']) != len(members) or set(values['order']) != set(members):
            raise ValidationError({'order': ['抽签须准确覆盖一个待决组，不能缺少或重复选手。']})
        versions = source_versions(t)
        if values['source_versions'] != versions:
            conflict('来源成绩已变化，请刷新最终排名。', 'stale_standings')
        # At most one open record per group and source version: re-recording until a preferred order appears is not allowed.
        if any(set(x.members) == set(members) and x.source_versions == versions for x in t.lotteries.filter(confirmed_at__isnull=True, voided_at__isnull=True)):
            conflict('该并列组已有待确认的抽签记录，请先确认或作废后再录入。', 'lottery_pending')
        return LotteryRecord.objects.create(tournament=t, created_by=user, rules_version=t.rules_version, **values)


def confirm_lottery(pk, lottery_id, user):
    with locked(pk) as (t, _):
        ready_final(t)
        row = get_object_or_404(LotteryRecord, pk=lottery_id, tournament=t)
        if row.voided_at:
            conflict('抽签记录已作废。', 'lottery_voided')
        _, groups = ranking(t)
        if row.confirmed_at or row.source_versions != source_versions(t) or set(row.members) not in [set(g) for g in groups]:
            conflict('抽签已确认或来源已过期。', 'lottery_conflict')
        row.confirmed_by, row.confirmed_at = user, timezone.now()
        row.save(update_fields=['confirmed_by', 'confirmed_at'])
        return row


def void_lottery(pk, lottery_id, user, reason):
    """Void an unconfirmed record with audit; it stays listed but never ranks."""
    with locked(pk, writable=False) as (t, _):
        if t.status == 'completed':
            conflict('赛事已完赛，抽签记录只读。', 'tournament_completed')
        row = get_object_or_404(LotteryRecord, pk=lottery_id, tournament=t)
        if row.confirmed_at:
            conflict('已确认的抽签不能作废。', 'lottery_conflict')
        if row.voided_at:
            conflict('抽签记录已作废。', 'lottery_voided')
        row.voided_by, row.voided_at, row.void_reason = user, timezone.now(), reason
        row.save(update_fields=['voided_by', 'voided_at', 'void_reason'])
        return row


def release_reservation(row, user, reason):
    # Keep the creation reason (e.g. fault replacement); audit the release separately.
    now = timezone.now()
    row.status, row.released_by, row.released_at, row.release_reason = 'released', user, now, reason
    row.save(update_fields=['status', 'released_by', 'released_at', 'release_reason'])
    if row.legacy_allocation_id:
        MachineAllocation.objects.filter(pk=row.legacy_allocation_id, status='active').update(status='released', released_by=user, released_at=now, release_reason=reason)


def replace_machine(pk, ordinal, user, machine_id, reason):
    with locked(pk) as (t, machines):
        bridge_legacy(t, user)
        if t.resource_state == 'historical_only':
            conflict('仅补录历史成绩的赛事不能占用新物理桌。', 'historical_only')
        table = get_object_or_404(TournamentTable, tournament=t, ordinal=ordinal)
        current = table.reservations.filter(status='active').first()
        if not current:
            conflict('此桌无有效预留，请走兼容复核。', 'resource_review_required')
        if current.machine_id == machine_id:
            conflict('目标物理桌未改变。', 'machine_unchanged')
        if machine_id not in machines or machines[machine_id].status != 'available' or machine_id in occupied_ids():
            conflict('目标物理桌不可用或已被占用。', 'machine_occupied')
        release_reservation(current, user, reason)
        Reservation.objects.create(table=table, machine=machines[machine_id], machine_no_snapshot=machines[machine_id].machine_no, created_by=user, source='fault_replacement_v1', reason=reason)


def review_legacy(pk, user, *, historical_only, machine_ids, reason):
    with locked(pk) as (t, machines):
        bridge_legacy(t, user)
        if t.resource_state != 'review_required':
            conflict('当前赛事无需兼容复核。', 'review_not_required')
        if historical_only:
            # May enter scores for existing final round, but cannot fabricate rounds.
            if not t.rounds.filter(round_number=t.round_count).exists() or machine_ids:
                raise ValidationError({'historical_only': ['仅已存在全部配置轮次且无需后续实体对局时可选。']})
            t.resource_state = 'historical_only'
        else:
            needed = t.participants.count() // 4
            if len(machine_ids) != needed or len(set(machine_ids)) != needed:
                raise ValidationError({'machine_ids': ['须为每个逻辑桌选择一个物理桌。']})
            tables = {x.ordinal: x for x in t.fixed_tables.all()}
            if any(ordinal not in tables for ordinal in range(1, needed + 1)):
                conflict('旧赛事逻辑桌结构不完整，需人工核对。', 'legacy_structure_invalid')
            for ordinal, machine_id in enumerate(machine_ids, 1):
                table = tables[ordinal]
                current = table.reservations.filter(status='active').first()
                if current and current.machine_id == machine_id and machine_id in machines and machines[machine_id].status == 'available':
                    continue
                if machine_id not in machines or machines[machine_id].status != 'available' or machine_id in occupied_ids():
                    conflict('复核目标已被占用或不可用，不会抢回旧设备。', 'machine_occupied')
                if current:
                    release_reservation(current, user, reason)
                Reservation.objects.create(table=table, machine=machines[machine_id], machine_no_snapshot=machines[machine_id].machine_no, created_by=user, source='legacy_review_v1', reason=reason)
            t.resource_state = 'fixed'
        t.compatibility_audit = {**t.compatibility_audit, 'reviewed_by': user.pk, 'reviewed_at': timezone.now().isoformat(), 'historical_only': historical_only, 'reason': reason}
        t.save()


def finish(pk, user, versions):
    with locked(pk) as (t, _):
        ready_final(t)
        if t.resource_state not in ('fixed', 'historical_only'):
            conflict('兼容复核尚未完成。', 'resource_review_required')
        if versions != source_versions(t):
            conflict('结果版本已变化，请刷新后确认。', 'stale_standings')
        rows, groups = ranking(t)
        if groups:
            conflict('仍有完全并列组须公开抽签并二次确认。', 'lottery_required')
        if not rows or rows[0]['rank'] != 1 or sum(r['rank'] == 1 for r in rows) != 1:
            conflict('未确定唯一冠军。', 'champion_unresolved')
        t.status, t.completed_by, t.completed_at = 'completed', user, timezone.now()
        t.champion_id = rows[0]['participant_id']
        t.final_snapshot = {'standings': rows, 'champion_id': t.champion_id, 'rules': rules(t), 'source_versions': versions, 'lottery_ids': sorted({row['lottery_id'] for row in rows if row.get('lottery_id') is not None}), 'completed_at': t.completed_at.isoformat(), 'completed_by': user.pk}
        t.save()
        for row in Reservation.objects.filter(table__tournament=t, status='active'):
            release_reservation(row, user, '正式完赛自动释放')
        # Includes any legacy active records not bridged (defensive, scoped).
        MachineAllocation.objects.filter(table__round__tournament=t, status='active').update(status='released', released_by=user, released_at=t.completed_at, release_reason='正式完赛自动释放')
        return t.final_snapshot
