"""Owner-managed player records; lock User then Profile, as tournament eligibility does."""
from contextlib import contextmanager
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models import F
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException

from .models import PlayerProfile


class PlayerConflict(APIException):
    status_code = 409

    def __init__(self, message, code='player_conflict'):
        self.default_code = code
        super().__init__(message, code)


def database_error(exc):
    if isinstance(exc, OperationalError) and (connection.vendor != 'sqlite' or 'locked' not in str(exc).lower()):
        raise exc
    raise PlayerConflict('选手记录正在变化，操作已回滚，请刷新后核对。') from None


def create_player(nickname):
    try:
        with transaction.atomic():
            user = get_user_model()(username='player_' + uuid4().hex, is_active=True, is_staff=False, is_superuser=False)
            user.set_unusable_password()
            user.save()
            profile = user.player_profile  # Same atomic signal path as existing identities.
            profile.nickname = nickname
            profile.save(update_fields=['nickname', 'updated_at'])
            return profile
    except (IntegrityError, OperationalError) as exc:
        database_error(exc)


def own_profile(user):
    """Account profile, lazily repaired for identities that predate the signal.

    Same semantics as signals.create_player_profile (nickname=username[:80]).
    FIRST statement writes the User row, then User -> Profile, like locked_player;
    a concurrent creator is serialized and get_or_create returns its row.
    """
    try:
        return user.player_profile
    except PlayerProfile.DoesNotExist:
        pass
    try:
        with transaction.atomic():
            get_user_model().objects.filter(pk=user.pk).update(is_active=F('is_active'))
            owner = get_object_or_404(get_user_model().objects.select_for_update(), pk=user.pk)
            return PlayerProfile.objects.get_or_create(user=owner, defaults={'nickname': owner.username[:80]})[0]
    except (IntegrityError, OperationalError) as exc:
        database_error(exc)


@contextmanager
def locked_player(pk):
    # Read only to identify the parent. The transaction's FIRST statement is a
    # write on that User, reserving SQLite's writer; PG then locks User->Profile.
    user_id = get_object_or_404(PlayerProfile, pk=pk).user_id
    try:
        with transaction.atomic():
            get_user_model().objects.filter(pk=user_id).update(is_active=F('is_active'))
            user = get_object_or_404(get_user_model().objects.select_for_update(), pk=user_id)
            profile = get_object_or_404(PlayerProfile.objects.select_for_update(), pk=pk, user=user)
            if user.is_staff or user.is_superuser:
                raise PlayerConflict('管理员账号档案不能作为普通选手维护。', 'administrator_profile_protected')
            yield profile, user
    except (IntegrityError, OperationalError, ProtectedError) as exc:
        database_error(exc)


def mutate_player(pk, *, nickname=None, action=None):
    with locked_player(pk) as (profile, user):
        if action == 'delete':
            if profile.tournament_entries.exists():
                raise PlayerConflict('此选手已被草稿或历史赛事引用，请归档以保留比赛记录。', 'player_referenced')
            # Delete ONLY the business profile. Retain its inactive identity row
            # so unrelated historic user audits can never be cascade-deleted.
            profile.delete()
            user.is_active = False
            user.save(update_fields=['is_active'])
            return None
        if action in ('archive', 'restore'):
            target = action == 'restore'
            if user.is_active == target:
                raise PlayerConflict('选手状态已变化，请刷新查看。', 'player_state_changed')
            user.is_active = target
            user.save(update_fields=['is_active'])
        if nickname is not None:
            profile.nickname = nickname
        profile.save(update_fields=['nickname', 'updated_at'])
        return profile
