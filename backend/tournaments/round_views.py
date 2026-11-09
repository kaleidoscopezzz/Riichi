from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from machines.models import MahjongMachine
from .models import Tournament, TournamentRound, RoundTable, RoundSeat, MachineAllocation
from .round_serializers import GenerateRoundSerializer, PairingPreviewSerializer, ReassignSerializer, ReleaseSerializer, RoundSerializer, TableSerializer, AllocationSerializer
from .round_services import change_allocation
from .competition_services import generate, occupied_ids
from .models import TournamentMachineReservation


def tables_query():
    return RoundTable.objects.select_related("round").prefetch_related(
        Prefetch("seats", queryset=RoundSeat.objects.select_related("participant")),
        Prefetch("allocations", queryset=MachineAllocation.objects.select_related("machine")),
    )


def rounds_query():
    return TournamentRound.objects.prefetch_related(Prefetch("tables", queryset=tables_query()))


def table_response(pk):
    return Response({"data": TableSerializer(get_object_or_404(tables_query(), pk=pk)).data}, headers={"Cache-Control": "no-store"})


class RoundListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        get_object_or_404(Tournament, pk=pk)
        rows = rounds_query().filter(tournament_id=pk)
        return Response({"data": {"results": RoundSerializer(rows, many=True).data}}, headers={"Cache-Control": "no-store"})

    def post(self, request, pk):
        serializer = GenerateRoundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = generate(pk, request.user, serializer.validated_data["round_number"], machine_ids=serializer.validated_data.get("machine_ids"), pairing_token=serializer.validated_data.get('pairing_token'), participant_groups=serializer.validated_data.get('participant_groups'))
        return Response({"data": RoundSerializer(rounds_query().get(pk=row.pk)).data}, status=201)


class PairingPreviewView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        from .pairing_plan import preview
        serializer = PairingPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({'data': preview(pk, request.user, serializer.validated_data['round_number'])}, headers={'Cache-Control': 'no-store'})


class RoundDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk, round_number):
        row = get_object_or_404(rounds_query(), tournament_id=pk, round_number=round_number)
        return Response({"data": RoundSerializer(row).data}, headers={"Cache-Control": "no-store"})


class TableDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        return table_response(pk)


class AllocationHistoryView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        table = get_object_or_404(tables_query(), pk=pk)
        return Response({"data": {"results": AllocationSerializer(table.allocations.all(), many=True).data}}, headers={"Cache-Control": "no-store"})


class ReassignView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        serializer = ReassignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        change_allocation(pk, request.user, machine_id=serializer.validated_data["machine_id"])
        return table_response(pk)


class ReleaseView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        serializer = ReleaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        change_allocation(pk, request.user, reason=serializer.validated_data["reason"])
        return table_response(pk)


class MachineResourceView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        active = {a.machine_id: a for a in MachineAllocation.objects.filter(status="active").select_related("table__round__tournament")}
        reservations = {r.machine_id: r for r in TournamentMachineReservation.objects.filter(status="active").select_related("table__tournament")}
        occupied = occupied_ids()
        results = []
        for machine in MahjongMachine.objects.exclude(status="retired"):
            allocation = active.get(machine.pk)
            results.append({"machine_id": machine.pk, "machine_no": machine.machine_no, "name": machine.name, "status": machine.status,
                "reservation": {"tournament_id": reservations[machine.pk].table.tournament_id, "tournament_name": reservations[machine.pk].table.tournament.name, "ordinal": reservations[machine.pk].table.ordinal} if machine.pk in reservations else None,
                "assignable": machine.status == "available" and machine.pk not in occupied,
                "active_allocation": {"id": allocation.pk, "table_id": allocation.table_id, "table_number": allocation.table.table_number, "round_number": allocation.table.round.round_number, "tournament_id": allocation.table.round.tournament_id, "tournament_name": allocation.table.round.tournament.name} if allocation else None})
        return Response({"data": {"results": results}}, headers={"Cache-Control": "no-store"})
