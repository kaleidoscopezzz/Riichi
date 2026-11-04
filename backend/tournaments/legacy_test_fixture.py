"""F0-05 data writer for migration/regression fixtures ONLY; never imported by runtime.
The old automatic machine selection is intentionally unavailable through services/API.
"""
import random
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from machines.locking import lock_machine_pool
from .models import Tournament, TournamentRound, RoundTable, RoundSeat, MachineAllocation
from .services import database_busy
from .round_services import conflict, validate_round_structure

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
            from .competition_services import occupied_ids
            occupied = occupied_ids()
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


