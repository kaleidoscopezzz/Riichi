from rest_framework import serializers

from common.api import StrictFieldsMixin
from .serializers import ExactInteger, UmaField, OkaField
from .pairing import TEAM_CHOICES
from .team_scheduling import MAX_TEAMS, MAX_MEMBERS, MAX_MATCHES


class TeamRosterWrite(StrictFieldsMixin, serializers.Serializer):
    id = ExactInteger(min_value=1, required=False)
    name = serializers.CharField(max_length=80)
    player_ids = serializers.ListField(child=ExactInteger(min_value=1), max_length=MAX_MEMBERS)
    captain_player_id = ExactInteger(min_value=1, allow_null=True, required=False)


class TeamTournamentWrite(StrictFieldsMixin, serializers.Serializer):
    competition_type = serializers.ChoiceField(choices=['team'], required=False, default='team')
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=3000, allow_blank=True, required=False)
    starting_points = ExactInteger(min_value=1, max_value=2147483647, required=False)
    return_points = ExactInteger(min_value=1, max_value=2147483647, required=False)
    uma = UmaField(required=False)
    oka_override = OkaField(required=False, allow_null=True)
    pairing_strategy = serializers.ChoiceField(choices=TEAM_CHOICES, required=False)
    schedule_mode = serializers.ChoiceField(choices=['free', 'positions'], required=False)
    total_matches = ExactInteger(min_value=1, max_value=MAX_MATCHES, allow_null=True, required=False)
    positions = serializers.ListField(child=serializers.CharField(max_length=80), min_length=1, max_length=32, required=False)
    games_per_position = ExactInteger(min_value=1, max_value=100, required=False)
    cycles = ExactInteger(min_value=1, max_value=100, required=False)
    teams = TeamRosterWrite(many=True, max_length=MAX_TEAMS, required=False)


class TeamTournamentUpdate(TeamTournamentWrite):
    revision = ExactInteger(min_value=0, required=False)


class ExplicitConfirm(StrictFieldsMixin, serializers.Serializer):
    confirmed = serializers.BooleanField()

    def validate_confirmed(self, value):
        if not value:
            raise serializers.ValidationError('需要明确二次确认。')
        return value


class TokenWrite(ExplicitConfirm):
    token = serializers.CharField(max_length=2000000)


class ResetWrite(ExplicitConfirm):
    revision = ExactInteger(min_value=0)
    reason = serializers.CharField(max_length=500)


class LineupSeat(StrictFieldsMixin, serializers.Serializer):
    team_id = ExactInteger(min_value=1)
    member_id = ExactInteger(min_value=1, allow_null=True)


class PlanWrite(StrictFieldsMixin, serializers.Serializer):
    version = ExactInteger(min_value=1)
    team_ids = serializers.ListField(child=ExactInteger(min_value=1), min_length=4, max_length=4, required=False)
    lineup = LineupSeat(many=True, max_length=4, required=False)
    captain_supplied = serializers.BooleanField(required=False, default=False)


class PlanVersion(StrictFieldsMixin, serializers.Serializer):
    match_id = ExactInteger(min_value=1)
    version = ExactInteger(min_value=1)


class PlansConfirm(ExplicitConfirm):
    plan_sources = PlanVersion(many=True, min_length=1, max_length=MAX_MATCHES, allow_empty=False)


class PlanWithdraw(ExplicitConfirm):
    version = ExactInteger(min_value=1)
    reason = serializers.CharField(max_length=500)


class RepresentativeWrite(StrictFieldsMixin, serializers.Serializer):
    revision = ExactInteger(min_value=0)
    team_id = ExactInteger(min_value=1)
    member_id = ExactInteger(min_value=1, allow_null=True)
    captain_supplied = serializers.BooleanField(required=False, default=False)
    withdraw_confirmed = serializers.BooleanField(required=False, default=False)
    reason = serializers.CharField(max_length=500, allow_blank=True, required=False, default='')


class BatchPreviewWrite(StrictFieldsMixin, serializers.Serializer):
    machine_ids = serializers.ListField(child=ExactInteger(min_value=1), min_length=1, max_length=4, required=False)


class RepresentativeSeat(StrictFieldsMixin, serializers.Serializer):
    team_id = ExactInteger(min_value=1)
    member_id = ExactInteger(min_value=1, allow_null=True)


class RepresentativesWrite(StrictFieldsMixin, serializers.Serializer):
    revision = ExactInteger(min_value=0)
    representatives = RepresentativeSeat(many=True, min_length=1, max_length=MAX_TEAMS, allow_empty=False)
    captain_supplied = serializers.BooleanField(required=False, default=False)
    withdraw_confirmed = serializers.BooleanField(required=False, default=False)
    reason = serializers.CharField(max_length=500, allow_blank=True, required=False, default='')


class SourceMember(StrictFieldsMixin, serializers.Serializer):
    id = ExactInteger(min_value=1)
    participant_id = ExactInteger(min_value=1)
    player_id = ExactInteger(min_value=1)
    display_name = serializers.CharField(max_length=80)
    is_captain = serializers.BooleanField()


class SourceTeam(StrictFieldsMixin, serializers.Serializer):
    id = ExactInteger(min_value=1)
    name = serializers.CharField(max_length=80)
    members = SourceMember(many=True, min_length=1, max_length=MAX_MEMBERS, allow_empty=False)


class SourceVersion(StrictFieldsMixin, serializers.Serializer):
    table_id = ExactInteger(min_value=1)
    version = ExactInteger(min_value=1)


class TeamSources(StrictFieldsMixin, serializers.Serializer):
    source_versions = SourceVersion(many=True, min_length=1, max_length=MAX_MATCHES, allow_empty=False)
    roster_snapshot = SourceTeam(many=True, min_length=4, max_length=MAX_TEAMS, allow_empty=False)
    plan_sources = PlanVersion(many=True, min_length=1, max_length=MAX_MATCHES, allow_empty=False)


class TeamFinishWrite(TeamSources):
    confirmed = serializers.BooleanField()
    validate_confirmed = ExplicitConfirm.validate_confirmed


class TeamLotteryWrite(TeamSources):
    entity_type = serializers.ChoiceField(choices=['team'])
    members = serializers.ListField(child=ExactInteger(min_value=1), min_length=2, max_length=MAX_TEAMS)
    order = serializers.ListField(child=ExactInteger(min_value=1), min_length=2, max_length=MAX_TEAMS)
    method = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=2000)
    drawn_at = serializers.DateTimeField()
