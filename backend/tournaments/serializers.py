from django.core.exceptions import ValidationError as ModelValidationError
from rest_framework import serializers

from common.api import StrictFieldsMixin
from .models import Tournament
from .rules import canonical_oka, canonical_uma
from .pairing import NEW_CHOICES, SUPPORTED_CHOICES, canonical_table_bonuses


class ExactInteger(serializers.IntegerField):
    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, int):
            self.fail("invalid")
        return super().to_internal_value(data)


class UmaField(serializers.Field):
    def to_internal_value(self, data):
        try:
            return canonical_uma(data)
        except ModelValidationError as exc:
            raise serializers.ValidationError(exc.messages) from None


class OkaField(serializers.Field):
    def to_internal_value(self, data):
        try:
            return canonical_oka(data)
        except ModelValidationError as exc:
            raise serializers.ValidationError(exc.messages) from None


class TableBonusesField(serializers.Field):
    def to_internal_value(self, data):
        try:
            return canonical_table_bonuses(data)
        except ModelValidationError as exc:
            raise serializers.ValidationError(exc.messages) from None


class TournamentWriteSerializer(StrictFieldsMixin, serializers.Serializer):
    competition_type = serializers.ChoiceField(choices=['individual'], required=False)
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=3000, allow_blank=True, required=False)
    round_count = ExactInteger(min_value=1, max_value=6)
    starting_points = ExactInteger(min_value=1, max_value=2147483647, required=False)
    return_points = ExactInteger(min_value=1, max_value=2147483647, required=False)
    uma = UmaField(required=False)
    oka_override = OkaField(required=False, allow_null=True)
    pairing_strategy = serializers.ChoiceField(choices=NEW_CHOICES, required=False)
    ranked_table_bonuses = TableBonusesField(required=False)
    score_tie_policy = serializers.ChoiceField(choices=["split_rank_bonus_v1"], required=False)
    champion_tiebreak_policy = serializers.ChoiceField(choices=["performance_v1"], required=False)
    rules_version = ExactInteger(min_value=1, max_value=2, required=False)


class ParticipantWriteSerializer(StrictFieldsMixin, serializers.Serializer):
    participant_ids = serializers.ListField(child=ExactInteger(min_value=1), max_length=16)
    # Optional optimistic concurrency token; omitted keeps the legacy last-write behaviour.
    revision = ExactInteger(min_value=0, max_value=2147483647, required=False)

    def validate_participant_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("同一选手不能重复参赛。")
        return value


class TournamentCreateSerializer(TournamentWriteSerializer):
    participant_ids = serializers.ListField(child=ExactInteger(min_value=1), max_length=16, required=False)

    def validate_participant_ids(self, value):
        return ParticipantWriteSerializer().validate_participant_ids(value)


class TournamentUpdateSerializer(TournamentCreateSerializer):
    # The service permits a withdrawn strategy only when preserving an existing one.
    pairing_strategy = serializers.ChoiceField(choices=SUPPORTED_CHOICES, required=False)
    revision = ExactInteger(min_value=0, max_value=2147483647, required=False)


class EmptySerializer(StrictFieldsMixin, serializers.Serializer):
    pass


class TournamentSerializer(serializers.ModelSerializer):
    oka = serializers.CharField(read_only=True)
    participant_count = serializers.SerializerMethodField()
    expected_table_count = serializers.SerializerMethodField()
    participants = serializers.SerializerMethodField()

    def to_representation(self, instance):
        if instance.competition_type == 'team':
            from .team_services import team_data
            return team_data(instance)
        return super().to_representation(instance)

    class Meta:
        model = Tournament
        fields = ["id", "name", "description", "competition_type", "round_count", "starting_points", "return_points", "uma", "oka", "oka_override", "pairing_strategy", "table_bonus_policy", "ranked_table_bonuses", "status", "created_by", "created_at", "updated_at", "started_at", "revision", "participant_count", "expected_table_count", "participants", "score_tie_policy", "champion_tiebreak_policy", "rules_version", "rules_source", "resource_state", "completed_at", "champion_id", "champion_team_id"]

    def get_participant_count(self, obj):
        return len(obj.participants.all())

    def get_expected_table_count(self, obj):
        count = self.get_participant_count(obj)
        return count // 4 if count in (4, 8, 12, 16) else None

    def get_participants(self, obj):
        # Internal technical usernames are never exposed; players are identified by IDs and nicknames.
        return [{"id": entry.id, "player_id": entry.player_id,
                 "display_name": entry.display_name_snapshot if obj.status != "draft" else entry.player.nickname,
                 "is_active": entry.player.user.is_active,
                 "eliminated_after_round": entry.eliminated_after_round,
                 "display_name_snapshot": entry.display_name_snapshot}
                for entry in obj.participants.all()]
