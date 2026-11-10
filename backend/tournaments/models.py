from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from .rules import default_uma, derive_oka, validate_oka, validate_uma
from .pairing import BONUS_POLICY, CHOICES as PAIRING_CHOICES, RANKED, TEAM_CHOICES, default_table_bonuses, validate_table_bonuses
from .team_scheduling import default_positions


class Tournament(models.Model):
    class CompetitionType(models.TextChoices):
        INDIVIDUAL = 'individual', '个人赛'
        TEAM = 'team', '团队赛'

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        STARTED = "started", "已启动"
        COMPLETED = "completed", "已完赛"

    name = models.CharField(max_length=120)
    competition_type = models.CharField(max_length=12, choices=CompetitionType, default=CompetitionType.INDIVIDUAL)
    description = models.TextField(max_length=3000, blank=True)
    round_count = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(6)])
    starting_points = models.PositiveIntegerField(default=25000, validators=[MinValueValidator(1), MaxValueValidator(2147483647)])
    return_points = models.PositiveIntegerField(default=30000, validators=[MinValueValidator(1), MaxValueValidator(2147483647)])
    uma = models.JSONField(default=default_uma, validators=[validate_uma])
    # NULL preserves automatic derivation, including every pre-0007 tournament.
    oka_override = models.CharField(max_length=64, null=True, blank=True, default=None, validators=[validate_oka])
    pairing_strategy = models.CharField(max_length=48, choices=PAIRING_CHOICES, default=RANKED)
    table_bonus_policy = models.CharField(max_length=40, default=BONUS_POLICY)
    ranked_table_bonuses = models.JSONField(default=default_table_bonuses, validators=[validate_table_bonuses])
    status = models.CharField(max_length=10, choices=Status, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_tournaments")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=0, editable=False)
    score_tie_policy = models.CharField(max_length=40, default="split_rank_bonus_v1")
    champion_tiebreak_policy = models.CharField(max_length=40, default="performance_v1")
    rules_version = models.PositiveSmallIntegerField(default=2)
    rules_source = models.CharField(max_length=80, default="created_v2")
    first_round_order = models.JSONField(blank=True, default=list)
    order_source = models.CharField(max_length=80, blank=True)
    resource_state = models.CharField(max_length=24, default="unselected")
    compatibility_audit = models.JSONField(blank=True, default=dict)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="completed_tournaments")
    champion = models.ForeignKey("TournamentParticipant", null=True, blank=True, on_delete=models.PROTECT, related_name="championships")
    champion_team = models.ForeignKey('TournamentTeam', null=True, blank=True, on_delete=models.PROTECT, related_name='championships')
    final_snapshot = models.JSONField(blank=True, default=dict)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(competition_type='individual', round_count__gte=1, round_count__lte=6) | Q(competition_type='team', round_count=1), name="tournament_round_range"),
            models.CheckConstraint(condition=Q(starting_points__gte=1, starting_points__lte=2147483647, return_points__gte=1, return_points__lte=2147483647), name="tournament_positive_points"),
            models.CheckConstraint(condition=Q(status="draft", started_at__isnull=True, completed_at__isnull=True, champion__isnull=True, champion_team__isnull=True) | Q(status="started", started_at__isnull=False, completed_at__isnull=True, champion__isnull=True, champion_team__isnull=True) | (Q(status="completed", started_at__isnull=False, completed_at__isnull=False, completed_by__isnull=False) & (Q(competition_type='individual', champion__isnull=False, champion_team__isnull=True) | Q(competition_type='team', champion__isnull=True, champion_team__isnull=False))), name="tournament_lifecycle"),
            models.CheckConstraint(condition=Q(name__regex=r"\S"), name="tournament_name_nonblank"),
            models.CheckConstraint(condition=Q(oka_override__isnull=True) | Q(rules_version=2, oka_override__regex=r"\A[+]?[0-9]+([.][0-9]+)?\Z"), name="tournament_oka_override_valid"),
            models.CheckConstraint(condition=Q(pairing_strategy__in=[value for value, _ in PAIRING_CHOICES]), name='tournament_pairing_strategy_valid'),
            models.CheckConstraint(condition=Q(competition_type='individual') & (Q(pairing_strategy='legacy_v1', table_bonus_policy='none') | (~Q(pairing_strategy='legacy_v1') & Q(table_bonus_policy=BONUS_POLICY))) | Q(competition_type='team', pairing_strategy__in=[value for value, _ in TEAM_CHOICES], table_bonus_policy='none'), name='tournament_table_bonus_policy_valid'),
            models.CheckConstraint(condition=Q(competition_type='individual', champion_tiebreak_policy='performance_v1') | Q(competition_type='team', champion_tiebreak_policy='team_performance_v1'), name='tournament_mode_champion_policy'),
        ]

    @property
    def oka(self):
        return self.oka_override if self.oka_override is not None else derive_oka(self.starting_points, self.return_points)


class TournamentParticipant(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.PROTECT, related_name="participants")
    player = models.ForeignKey("players.PlayerProfile", on_delete=models.PROTECT, related_name="tournament_entries")
    display_name_snapshot = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Participation and all prior seats survive elimination. NULL is still in play.
    eliminated_after_round = models.PositiveSmallIntegerField(null=True, blank=True, default=None)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["tournament", "player"], name="unique_tournament_player"),
            models.CheckConstraint(condition=Q(eliminated_after_round__isnull=True) | Q(eliminated_after_round__gte=1, eliminated_after_round__lte=5), name='participant_elimination_round_range'),
        ]


class TournamentRound(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.PROTECT, related_name="rounds")
    competition_type = models.CharField(max_length=12, choices=Tournament.CompetitionType, default='individual')
    round_number = models.PositiveSmallIntegerField()
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="generated_rounds")
    created_at = models.DateTimeField(auto_now_add=True)
    generation_snapshot = models.JSONField(blank=True, default=dict)

    class Meta:
        ordering = ["round_number"]
        constraints = [
            models.UniqueConstraint(fields=["tournament", "round_number"], name="unique_tournament_round"),
            models.CheckConstraint(condition=Q(competition_type='individual', round_number__gte=1, round_number__lte=6) | Q(competition_type='team', round_number__gte=1, round_number__lte=10000), name="round_number_range"),
        ]


class EliminationRecord(models.Model):
    round = models.OneToOneField(TournamentRound, on_delete=models.PROTECT, related_name='elimination')
    participant_ids = models.JSONField()
    source_versions = models.JSONField()
    participant_statuses = models.JSONField()
    standings_snapshot = models.JSONField()
    lottery_ids = models.JSONField(default=list)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='confirmed_eliminations')
    confirmed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['round__round_number']


class RoundTable(models.Model):
    round = models.ForeignKey(TournamentRound, on_delete=models.PROTECT, related_name="tables")
    table_number = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    tournament_table = models.ForeignKey("TournamentTable", null=True, blank=True, on_delete=models.PROTECT, related_name="round_tables")
    machine_snapshot = models.JSONField(blank=True, default=dict)
    base_bonus = models.CharField(max_length=64, default='0', validators=[validate_oka])
    bonus_source = models.CharField(max_length=48, default='legacy_zero')

    class Meta:
        ordering = ["table_number"]
        constraints = [
            models.UniqueConstraint(fields=["round", "table_number"], name="unique_round_table"),
            models.CheckConstraint(condition=Q(table_number__gte=1, table_number__lte=4), name="table_number_range"),
        ]


class RoundSeat(models.Model):
    class Wind(models.TextChoices):
        EAST = "east", "东"
        SOUTH = "south", "南"
        WEST = "west", "西"
        NORTH = "north", "北"

    round = models.ForeignKey(TournamentRound, on_delete=models.PROTECT, related_name="seats")
    table = models.ForeignKey(RoundTable, on_delete=models.PROTECT, related_name="seats")
    participant = models.ForeignKey(TournamentParticipant, on_delete=models.PROTECT, related_name="round_seats")
    seat_wind = models.CharField(max_length=5, choices=Wind)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.table.round_id != self.round_id:
            raise ValidationError({"table": "逻辑桌与座次必须属于同一轮。"})
        if self.participant.tournament_id != self.round.tournament_id:
            raise ValidationError({"participant": "不能安排其他赛事的参赛者。"})

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["table", "seat_wind"], name="unique_table_wind"),
            models.UniqueConstraint(fields=["round", "participant"], name="unique_round_participant"),
            models.CheckConstraint(condition=Q(seat_wind__in=["east", "south", "west", "north"]), name="seat_wind_valid"),
        ]


class MachineAllocation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "占用中"
        RELEASED = "released", "已释放"

    table = models.ForeignKey(RoundTable, on_delete=models.PROTECT, related_name="allocations")
    machine = models.ForeignKey("machines.MahjongMachine", on_delete=models.PROTECT, related_name="allocations")
    status = models.CharField(max_length=8, choices=Status, default=Status.ACTIVE)
    allocated_at = models.DateTimeField(auto_now_add=True)
    allocated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="machine_allocations")
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="machine_releases")
    release_reason = models.CharField(max_length=500, blank=True)
    machine_no_snapshot = models.CharField(max_length=3)

    class Meta:
        ordering = ["allocated_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["machine"], condition=Q(status="active"), name="unique_active_machine"),
            models.UniqueConstraint(fields=["table"], condition=Q(status="active"), name="unique_active_table"),
            models.CheckConstraint(condition=Q(status="active", released_at__isnull=True, released_by__isnull=True, release_reason="") | Q(status="released", released_at__isnull=False, released_by__isnull=False), name="allocation_release_state"),
        ]


class TournamentTable(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.PROTECT, related_name='fixed_tables')
    ordinal = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['ordinal']
        constraints = [models.UniqueConstraint(fields=['tournament', 'ordinal'], name='unique_fixed_table'), models.CheckConstraint(condition=Q(ordinal__gte=1, ordinal__lte=4), name='fixed_table_range')]


class TournamentMachineReservation(models.Model):
    table = models.ForeignKey(TournamentTable, on_delete=models.PROTECT, related_name='reservations')
    machine = models.ForeignKey('machines.MahjongMachine', on_delete=models.PROTECT, related_name='reservations')
    legacy_allocation = models.OneToOneField(MachineAllocation, null=True, blank=True, on_delete=models.PROTECT, related_name='reservation_bridge')
    status = models.CharField(max_length=8, default='active')
    source = models.CharField(max_length=40, default='explicit_selection_v1')
    machine_no_snapshot = models.CharField(max_length=3)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='table_reservations')
    created_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='reservation_releases')
    reason = models.CharField(max_length=500, blank=True)
    # Creation reason stays in `reason`; release writes only this field.
    release_reason = models.CharField(max_length=500, blank=True, default='')

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['table'], condition=Q(status='active'), name='unique_reserved_table'),
            models.CheckConstraint(condition=Q(status='active', released_at__isnull=True, released_by__isnull=True) | Q(status='released', released_at__isnull=False, released_by__isnull=False), name='reservation_release_state'),
        ]


class TableResult(models.Model):
    table = models.OneToOneField(RoundTable, on_delete=models.PROTECT, related_name='result')
    status = models.CharField(max_length=10, default='draft')
    version = models.PositiveIntegerField(default=1)
    # Existing participant IDs -> signed integer points or null. Validated by service.
    points = models.JSONField(blank=True, default=dict)
    scores = models.JSONField(blank=True, default=list)
    rule_snapshot = models.JSONField(blank=True, default=dict)
    edited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='edited_results')
    edited_at = models.DateTimeField(auto_now=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='confirmed_results')
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(status='draft', confirmed_at__isnull=True, confirmed_by__isnull=True) | Q(status='confirmed', confirmed_at__isnull=False, confirmed_by__isnull=False), name='result_confirmation_state')]


class TableResultCorrection(models.Model):
    result = models.ForeignKey(TableResult, on_delete=models.PROTECT, related_name='corrections')
    from_version = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    to_version = models.PositiveIntegerField(validators=[MinValueValidator(2)])
    before_snapshot = models.JSONField()
    after_snapshot = models.JSONField()
    corrected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='result_corrections')
    corrected_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=500, blank=True, default='')

    class Meta:
        ordering = ['-to_version', '-id']
        constraints = [
            models.UniqueConstraint(fields=['result', 'from_version'], name='unique_result_correction_from'),
            models.UniqueConstraint(fields=['result', 'to_version'], name='unique_result_correction_to'),
            models.CheckConstraint(condition=Q(from_version__gte=1, to_version=models.F('from_version') + 1), name='result_correction_version_step'),
        ]


class LotteryRecord(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.PROTECT, related_name='lotteries')
    entity_type = models.CharField(max_length=12, choices=[('participant', '个人'), ('team', '团队')], default='participant')
    roster_snapshot = models.JSONField(default=list, blank=True)
    plan_sources = models.JSONField(default=list, blank=True)
    source_versions = models.JSONField()
    members = models.JSONField()
    order = models.JSONField()
    method = models.CharField(max_length=200)
    description = models.CharField(max_length=2000)
    drawn_at = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='recorded_lotteries')
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='confirmed_lotteries')
    confirmed_at = models.DateTimeField(null=True)
    rules_version = models.PositiveSmallIntegerField(default=1)
    purpose = models.CharField(max_length=12, choices=[('final', '最终名次'), ('elimination', '淘汰边界')], default='final')
    elimination_round = models.ForeignKey(TournamentRound, null=True, blank=True, on_delete=models.PROTECT, related_name='elimination_lotteries')
    # Empty only on legacy final draws made before elimination was supported.
    participant_statuses = models.JSONField(default=list, blank=True)
    # Voided drafts stay as public audit; only confirmed records ever rank.
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='voided_lotteries')
    voided_at = models.DateTimeField(null=True)
    void_reason = models.CharField(max_length=500, blank=True, default='')

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(voided_at__isnull=True, voided_by__isnull=True, void_reason='') | (Q(voided_at__isnull=False, voided_by__isnull=False, confirmed_at__isnull=True) & ~Q(void_reason='')), name='lottery_void_state'),
            models.CheckConstraint(condition=Q(purpose='final', elimination_round__isnull=True) | Q(purpose='elimination', elimination_round__isnull=False), name='lottery_purpose_round_valid'),
            models.CheckConstraint(condition=Q(entity_type='participant') | Q(entity_type='team', purpose='final', elimination_round__isnull=True), name='lottery_entity_scope_valid'),
        ]


class TournamentTeam(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.PROTECT, related_name='teams')
    name = models.CharField(max_length=80)
    name_snapshot = models.CharField(max_length=80, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        constraints = [models.UniqueConstraint(fields=['tournament', 'name'], condition=Q(active=True), name='unique_active_team_name')]


class TeamMember(models.Model):
    team = models.ForeignKey(TournamentTeam, on_delete=models.PROTECT, related_name='members')
    participant = models.OneToOneField(TournamentParticipant, on_delete=models.PROTECT, related_name='team_membership')
    active = models.BooleanField(default=True)
    is_captain = models.BooleanField(default=False)

    class Meta:
        ordering = ['id']


class TeamCompetitionSettings(models.Model):
    tournament = models.OneToOneField(Tournament, on_delete=models.PROTECT, related_name='team_settings')
    schedule_mode = models.CharField(max_length=12, choices=[('free', '自由场次'), ('positions', '固定位置循环')], default='free')
    total_matches = models.PositiveIntegerField(null=True, blank=True)
    positions = models.JSONField(default=default_positions)
    games_per_position = models.PositiveSmallIntegerField(default=2)
    cycles = models.PositiveSmallIntegerField(default=1)
    schedule_revision = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(schedule_mode='free', total_matches__isnull=False, total_matches__gte=1, total_matches__lte=10000) | Q(schedule_mode='positions', total_matches__isnull=True, games_per_position__gte=1, games_per_position__lte=100, cycles__gte=1, cycles__lte=100), name='team_schedule_config_valid')]


class TeamStage(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.PROTECT, related_name='team_stages')
    schedule_revision = models.PositiveIntegerField()
    stage_number = models.PositiveIntegerField()
    cycle = models.PositiveSmallIntegerField()
    position_index = models.PositiveSmallIntegerField()
    position_label = models.CharField(max_length=80)
    games_per_team = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['stage_number']
        constraints = [models.UniqueConstraint(fields=['tournament', 'schedule_revision', 'stage_number'], name='unique_team_stage')]


class TeamStageRepresentative(models.Model):
    stage = models.ForeignKey(TeamStage, on_delete=models.PROTECT, related_name='representatives')
    team = models.ForeignKey(TournamentTeam, on_delete=models.PROTECT, related_name='stage_representatives')
    member = models.ForeignKey(TeamMember, null=True, blank=True, on_delete=models.PROTECT, related_name='stage_appearances')
    locked = models.BooleanField(default=False)
    captain_supplied = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['stage', 'team'], name='unique_stage_representative')]


class TeamMatchPlan(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.PROTECT, related_name='team_matches')
    schedule_revision = models.PositiveIntegerField()
    match_number = models.PositiveIntegerField()
    stage = models.ForeignKey(TeamStage, null=True, blank=True, on_delete=models.PROTECT, related_name='matches')
    team_ids = models.JSONField(default=list)
    lineup = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)
    captain_supplied = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=[('draft', '计划草稿'), ('confirmed', '计划已确认'), ('started', '已开场'), ('voided', '计划已撤销')], default='draft')
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='confirmed_team_plans')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    table = models.OneToOneField(RoundTable, null=True, blank=True, on_delete=models.PROTECT, related_name='team_match')

    class Meta:
        ordering = ['match_number', 'id']
        constraints = [
            models.UniqueConstraint(fields=['tournament', 'schedule_revision', 'match_number'], name='unique_team_match_number'),
            models.CheckConstraint(condition=Q(status='draft', confirmed_by__isnull=True, confirmed_at__isnull=True, table__isnull=True) | Q(status='confirmed', confirmed_by__isnull=False, confirmed_at__isnull=False, table__isnull=True) | Q(status='started', confirmed_by__isnull=False, confirmed_at__isnull=False, table__isnull=False) | Q(status='voided', table__isnull=True), name='team_plan_state_valid'),
        ]


class TeamAuditRecord(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.PROTECT, related_name='team_audits')
    action = models.CharField(max_length=48)
    revision = models.PositiveIntegerField()
    before_snapshot = models.JSONField(default=dict)
    after_snapshot = models.JSONField(default=dict)
    reason = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='team_audits')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
