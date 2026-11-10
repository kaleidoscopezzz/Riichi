"""Legacy allocation history and structure validation. New writes use competition_services."""
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from machines.locking import lock_machine_pool
from machines.models import MahjongMachine
from .models import RoundTable, RoundSeat, MachineAllocation
from .services import TournamentConflict, database_busy


def conflict(message, code):
    raise TournamentConflict(message, code)


def validate_round_structure(round):
    """Cross-table and exact-count checks, intentionally not claimed as SQL CHECKs."""
    participants = set(round.tournament.participants.filter(
        Q(eliminated_after_round__isnull=True) | Q(eliminated_after_round__gte=round.round_number)
    ).values_list("pk", flat=True))
    tables = list(round.tables.all())
    seats = list(round.seats.select_related("table", "participant"))
    if round.tournament.status not in ("started", "completed") or not 1 <= round.round_number <= round.tournament.round_count:
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


def change_allocation(table_id, user, *, machine_id=None, reason=""):
    try:
        with transaction.atomic():
            machines = {m.pk: m for m in lock_machine_pool()}
            table = get_object_or_404(RoundTable, pk=table_id)
            if table.round.tournament.fixed_tables.exists():
                conflict("赛事已接入固定选桌；请使用故障替换或正式完赛，不能单轮释放。", "fixed_reservation_protected")
            from .competition_services import occupied_ids
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
                if machine_id in occupied_ids():
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
