from django.db import IntegrityError, OperationalError, connection, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException

from .models import MahjongMachine
from .locking import lock_machine_pool


class MachineConflict(APIException):
    status_code = 409

    def __init__(self, message, code):
        self.default_code = code
        super().__init__(message, code)


def database_busy(exc):
    if connection.vendor == "sqlite" and "locked" in str(exc).lower():
        raise MachineConflict("设备正在被其他请求更新，请刷新列表后重试。", "machine_busy") from None
    raise exc


def create_machine(values):
    try:
        with transaction.atomic():
            return MahjongMachine.objects.create(**values)
    except IntegrityError:
        raise MachineConflict("现役设备编号已存在，请使用其他编号。", "duplicate_machine_no") from None
    except OperationalError as exc:
        database_busy(exc)


def change_machine(machine_id, values=None, *, retire=False):
    try:
        with transaction.atomic():
            lock_machine_pool()
            machine = get_object_or_404(MahjongMachine, pk=machine_id)
            if machine.status == MahjongMachine.Status.RETIRED:
                raise MachineConflict("设备已经退役，不能重复退役。" if retire else "已退役设备仅供查看，不能编辑或重新启用。", "already_retired" if retire else "retired_readonly")
            changes = {"status": "retired", "capacity_slot": None} if retire else dict(values)
            if changes.get("status", machine.status) != "available":
                from tournaments.models import MachineAllocation, TournamentMachineReservation
                if MachineAllocation.objects.filter(machine=machine, status="active").exists() or TournamentMachineReservation.objects.filter(machine=machine, status="active").exists():
                    raise MachineConflict("设备正被逻辑桌占用，请先确认释放后再维护、停用或退役。", "machine_in_use")
            changes["updated_at"] = timezone.now()
            # SQLite does not implement SELECT FOR UPDATE. The conditional write
            # also guards the terminal state if a retirement races with an edit.
            updated = MahjongMachine.objects.filter(pk=machine_id).exclude(status="retired").update(**changes)
            if not updated:
                raise MachineConflict("设备状态已变化，请刷新列表。", "machine_changed")
            machine.refresh_from_db()
            return machine
    except IntegrityError:
        raise MachineConflict("现役设备编号已存在，请使用其他编号。", "duplicate_machine_no") from None
    except OperationalError as exc:
        database_busy(exc)
