from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from .rules import default_uma, derive_oka, validate_uma


class Tournament(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        STARTED = "started", "已启动"
        COMPLETED = "completed", "已完赛"

    name = models.CharField(max_length=120)
    description = models.TextField(max_length=3000, blank=True)
    round_count = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(6)])
    starting_points = models.PositiveIntegerField(default=25000, validators=[MinValueValidator(1), MaxValueValidator(2147483647)])
    return_points = models.PositiveIntegerField(default=30000, validators=[MinValueValidator(1), MaxValueValidator(2147483647)])
    uma = models.JSONField(default=default_uma, validators=[validate_uma])
    status = models.CharField(max_length=10, choices=Status, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_tournaments")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=0, editable=False)
    score_tie_policy = models.CharField(max_length=40, default="split_rank_bonus_v1")
    champion_tiebreak_policy = models.CharField(max_length=40, default="performance_v1")
    rules_version = models.PositiveSmallIntegerField(default=1)
    rules_source = models.CharField(max_length=80, default="created_v1")
    first_round_order = models.JSONField(blank=True, default=list)
    order_source = models.CharField(max_length=80, blank=True)
    resource_state = models.CharField(max_length=24, default="unselected")
    compatibility_audit = models.JSONField(blank=True, default=dict)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="completed_tournaments")
    champion = models.ForeignKey("TournamentParticipant", null=True, blank=True, on_delete=models.PROTECT, related_name="championships")
    final_snapshot = models.JSONField(blank=True, default=dict)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(round_count__gte=1, round_count__lte=6), name="tournament_round_range"),
            models.CheckConstraint(condition=Q(starting_points__gte=1, starting_points__lte=2147483647, return_points__gte=1, return_points__lte=2147483647), name="tournament_positive_points"),
            models.CheckConstraint(condition=Q(status="draft", started_at__isnull=True, completed_at__isnull=True, champion__isnull=True) | Q(status="started", started_at__isnull=False, completed_at__isnull=True, champion__isnull=True) | Q(status="completed", started_at__isnull=False, completed_at__isnull=False, completed_by__isnull=False, champion__isnull=False), name="tournament_lifecycle"),
            models.CheckConstraint(condition=Q(name__regex=r"\S"), name="tournament_name_nonblank"),
        ]

    @property
    def oka(self):
        return derive_oka(self.starting_points, self.return_points)


class TournamentParticipant(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.PROTECT, related_name="participants")
    player = models.ForeignKey("players.PlayerProfile", on_delete=models.PROTECT, related_name="tournament_entries")
    display_name_snapshot = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["tournament", "player"], name="unique_tournament_player")]


class TournamentRound(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.PROTECT, related_name="rounds")
    round_number = models.PositiveSmallIntegerField()
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="generated_rounds")
    created_at = models.DateTimeField(auto_now_add=True)
    generation_snapshot = models.JSONField(blank=True, default=dict)

    class Meta:
        ordering = ["round_number"]
        constraints = [
            models.UniqueConstraint(fields=["tournament", "round_number"], name="unique_tournament_round"),
            models.CheckConstraint(condition=Q(round_number__gte=1, round_number__lte=6), name="round_number_range"),
        ]


class RoundTable(models.Model):
    round = models.ForeignKey(TournamentRound, on_delete=models.PROTECT, related_name="tables")
    table_number = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    tournament_table = models.ForeignKey("TournamentTable", null=True, blank=True, on_delete=models.PROTECT, related_name="round_tables")
    machine_snapshot = models.JSONField(blank=True, default=dict)

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

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['machine'], condition=Q(status='active'), name='unique_reserved_machine'),
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


class LotteryRecord(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.PROTECT, related_name='lotteries')
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
