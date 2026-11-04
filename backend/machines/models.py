from django.db import models
from django.db.models import Q


class MahjongMachine(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "可用"
        MAINTENANCE = "maintenance", "维护中"
        DISABLED = "disabled", "停用"
        RETIRED = "retired", "已退役"

    machine_no = models.CharField(max_length=3)
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.AVAILABLE)
    description = models.TextField(max_length=2000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Read-only legacy slot. New machines use NULL; no capacity limit.
    capacity_slot = models.PositiveSmallIntegerField(null=True, unique=True, editable=False)

    class Meta:
        ordering = ["machine_no", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(status__in=["available", "maintenance", "disabled", "retired"]), name="machine_valid_status"),
            models.CheckConstraint(condition=Q(machine_no__regex=r"^[0-9]{3}$"), name="machine_number_format"),
            models.CheckConstraint(condition=~Q(machine_no__regex=r"[^0-9]"), name="machine_number_digits_only"),
            models.CheckConstraint(condition=Q(name__regex=r"\S"), name="machine_name_not_blank"),
            models.UniqueConstraint(fields=["machine_no"], condition=~Q(status="retired"), name="machine_active_number_unique"),
        ]
