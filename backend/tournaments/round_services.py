"""First-round seating and physical resources only; no scores/round completion."""
import random
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from machines.locking import lock_machine_pool
from machines.models import MahjongMachine
from .models import Tournament, TournamentRound, RoundTable, RoundSeat, MachineAllocation
from .services import TournamentConflict, database_busy


def conflict(message, code):
    raise TournamentConflict(message, code)


def validate_round_structure(round):
    """Cross-table and exact-count checks, intentionally not claimed as SQL CHECKs."""
    participants = set(round.tournament.participants.values_list("pk", flat=True))
    tables = list(round.tables.all())
    seats = list(round.seats.select_related("table", "participant"))
    if round.tournament.status != "started" or not 1 <= round.round_number <= round.tournament.round_count:
        raise ValidationError({"round_number": ["轮次与赛事状态不兼容。"]})
    if len(participants) not in (4, 8, 12, 16) or len(tables) != len(participants) // 4 or {t.table_number for t in tables} != set(range(1, len(tables) + 1)):
        raise ValidationError({"participants": ["桌数与冻结名单不完整。"]})
    if len(seats) != len(participants) or {s.participant_id for s in seats} != participants:
        raise ValidationError({"participants": ["每名参赛者必须恰好安排一次。"]})
    for seat in seats:
        try:
            seat.clean()
        except ModelValidationError as exc:
            raise ValidationError(exc.message_dict) from None
    for table in tables:
        table_seats = [s for s in seats if s.table_id == table.pk]
        if len(table_seats) != 4 or {s.seat_wind for s in table_seats} != set(RoundSeat.Wind.values):
            raise ValidationError({"seats": ["每桌必须具有东南西北四名选手。"]})


def generate_first_round(tournament_id, user, round_number=1, *, rng=None):
    if round_number != 1:
        conflict("本阶段仅能生成第一轮，后续轮次须等待已确认成绩和累计积分。", "later_round_unavailable")
    try:
        with transaction.atomic():
            machines = lock_machine_pool()  # pool PK order -> tournament -> new children
            Tournament.objects.filter(pk=tournament_id).update(revision=F("revision") + 1)
            tournament = get_object_or_404(Tournament, pk=tournament_id)
            if tournament.status != "started":
                conflict("只有已启动赛事可以生成第一轮。", "tournament_not_started")
            if tournament.rounds.exists():
                conflict("第一轮已经生成，不能覆盖已有分桌。", "round_already_generated")
            participants = list(tournament.participants.all())
            if len(participants) not in (4, 8, 12, 16) or tournament.round_count < 1 or any(not p.display_name_snapshot for p in participants):
                raise ValidationError({"participants": ["赛事冻结名单或轮数无效。"]})
            occupied = set(MachineAllocation.objects.filter(status="active").values_list("machine_id", flat=True))
            free = sorted([m for m in machines if m.status == "available" and m.pk not in occupied], key=lambda m: (m.machine_no, m.pk))
            needed = len(participants) // 4
            if len(free) < needed:
                conflict(f"需要{needed}台空闲可用设备，当前仅{len(free)}台，未生成任何轮次。", "insufficient_machines")
            (rng if rng is not None else random.SystemRandom()).shuffle(participants)
            round = TournamentRound.objects.create(tournament=tournament, round_number=1, generated_by=user)
            for index in range(needed):
                table = RoundTable.objects.create(round=round, table_number=index + 1)
                for wind, participant in zip(RoundSeat.Wind.values, participants[index * 4:index * 4 + 4], strict=True):
                    seat = RoundSeat(round=round, table=table, participant=participant, seat_wind=wind)
                    seat.clean()
                    seat.save()
                MachineAllocation.objects.create(table=table, machine=free[index], allocated_by=user, machine_no_snapshot=free[index].machine_no)
            validate_round_structure(round)
            return round
    except OperationalError as exc:
        database_busy(exc)
    except IntegrityError:
        conflict("设备或轮次已被其他请求更新，请刷新查看。", "allocation_conflict")


def change_allocation(table_id, user, *, machine_id=None, reason=""):
    try:
        with transaction.atomic():
            machines = {m.pk: m for m in lock_machine_pool()}
            table = get_object_or_404(RoundTable, pk=table_id)
            current = table.allocations.filter(status="active").first()
            if current is None:
                conflict("此桌设备已释放，本阶段不支持重新开启占用。", "allocation_released")
            if machine_id is not None:
                target = machines.get(machine_id)
                if target is None:
                    get_object_or_404(MahjongMachine, pk=machine_id)
                    conflict("设备资源池已变化，请刷新后重新选择。", "allocation_conflict")
                if target.status != "available":
                    conflict("目标设备不是可用状态。", "machine_unavailable")
                if current.machine_id == machine_id:
                    conflict("该设备已分配给此桌，无需调整。", "machine_unchanged")
                if MachineAllocation.objects.filter(machine_id=machine_id, status="active").exists():
                    conflict("目标设备已被其他逻辑桌占用。", "machine_occupied")
            current.status = "released"
            current.released_at = timezone.now()
            current.released_by = user
            current.release_reason = "调整物理设备" if machine_id is not None else reason
            current.save(update_fields=["status", "released_at", "released_by", "release_reason"])
            if machine_id is not None:
                return MachineAllocation.objects.create(table=table, machine=target, machine_no_snapshot=target.machine_no, allocated_by=user)
            return current
    except OperationalError as exc:
        database_busy(exc)
    except IntegrityError:
        conflict("设备分配发生冲突，原有占用已保留，请刷新查看。", "allocation_conflict")
