from rest_framework import serializers
from common.api import StrictFieldsMixin
from .serializers import ExactInteger
from .models import MachineAllocation, RoundTable, TournamentRound


class GenerateRoundSerializer(StrictFieldsMixin, serializers.Serializer):
    round_number = ExactInteger(min_value=1, max_value=6)
    machine_ids = serializers.ListField(child=ExactInteger(min_value=1), max_length=4, required=False)
    pairing_token = serializers.CharField(max_length=24000, required=False)
    participant_groups = serializers.ListField(child=serializers.ListField(child=ExactInteger(min_value=1), min_length=4, max_length=4), min_length=1, max_length=4, required=False)


class PairingPreviewSerializer(StrictFieldsMixin, serializers.Serializer):
    round_number = ExactInteger(min_value=1, max_value=6)


class ReassignSerializer(StrictFieldsMixin, serializers.Serializer):
    machine_id = ExactInteger(min_value=1)


class ReleaseSerializer(StrictFieldsMixin, serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class AllocationSerializer(serializers.ModelSerializer):
    machine_id = serializers.IntegerField(read_only=True)
    machine_no = serializers.CharField(source="machine.machine_no", read_only=True)
    machine_status = serializers.CharField(source="machine.status", read_only=True)

    class Meta:
        model = MachineAllocation
        fields = ["id", "table_id", "machine_id", "machine_no", "machine_no_snapshot", "machine_status", "status", "allocated_at", "allocated_by", "released_at", "released_by", "release_reason"]


class TableSerializer(serializers.ModelSerializer):
    round_number = serializers.IntegerField(source="round.round_number", read_only=True)
    tournament_id = serializers.IntegerField(source="round.tournament_id", read_only=True)
    seats = serializers.SerializerMethodField()
    active_allocation = serializers.SerializerMethodField()
    allocation_history = serializers.SerializerMethodField()
    result = serializers.SerializerMethodField()

    class Meta:
        model = RoundTable
        fields = ["id", "round_id", "round_number", "tournament_id", "table_number", "seats", "active_allocation", "allocation_history", "created_at", "tournament_table_id", "machine_snapshot", "base_bonus", "bonus_source", "result"]

    def get_result(self, obj):
        from .competition_services import result_data
        return result_data(obj)

    def get_seats(self, obj):
        order = {wind: i for i, wind in enumerate(["east", "south", "west", "north"])}
        return [{"id": seat.id, "participant_id": seat.participant_id, "player_id": seat.participant.player_id, "display_name": seat.participant.display_name_snapshot, "seat_wind": seat.seat_wind} for seat in sorted(obj.seats.all(), key=lambda s: order[s.seat_wind])]

    def get_active_allocation(self, obj):
        active = next((row for row in obj.allocations.all() if row.status == "active"), None)
        return AllocationSerializer(active).data if active else None

    def get_allocation_history(self, obj):
        return AllocationSerializer(obj.allocations.all(), many=True).data


class RoundSerializer(serializers.ModelSerializer):
    tables = TableSerializer(many=True, read_only=True)

    class Meta:
        model = TournamentRound
        fields = ["id", "tournament_id", "round_number", "generated_at", "generated_by", "created_at", "tables", "generation_snapshot"]
