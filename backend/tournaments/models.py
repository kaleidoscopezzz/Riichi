from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from .rules import default_uma, derive_oka, validate_uma


class Tournament(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        STARTED = "started", "已启动"

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

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(round_count__gte=1, round_count__lte=6), name="tournament_round_range"),
            models.CheckConstraint(condition=Q(starting_points__gte=1, starting_points__lte=2147483647, return_points__gte=1, return_points__lte=2147483647), name="tournament_positive_points"),
            models.CheckConstraint(condition=Q(status="draft", started_at__isnull=True) | Q(status="started", started_at__isnull=False), name="tournament_lifecycle"),
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
