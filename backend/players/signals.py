from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PlayerProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_player_profile(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        PlayerProfile.objects.create(user=instance, nickname=instance.username[:80])
