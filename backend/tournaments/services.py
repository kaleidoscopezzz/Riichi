from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import OperationalError, connection, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from players.models import PlayerProfile
from .models import Tournament, TournamentParticipant
from .rules import canonical_oka, canonical_uma
from .scoring import rules
from .pairing import LEGACY, RANKED, NEW_CHOICES, SUPPORTED_CHOICES, canonical_table_bonuses


class TournamentConflict(APIException):
    status_code = 409

    def __init__(self, message, code="tournament_frozen"):
        self.default_code = code
        super().__init__(message, code)


def player_rows(ids):
    if len(ids) > 16 or len(ids) != len(set(ids)):
        raise ValidationError({"participant_ids": ["最多16名选手，不能重复选择。"]})
    # Lock account validity and nickname sources on PostgreSQL. SQLite's parent
    # write already holds the database write reservation before these reads.
    users = list(get_user_model().objects.select_for_update().filter(player_profile__id__in=ids).order_by("pk"))
    profiles = list(PlayerProfile.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
    if len(profiles) != len(ids) or any(not user.is_active or user.is_staff or user.is_superuser for user in users):
        raise ValidationError({"participant_ids": ["名单包含不存在、已归档或管理员档案，请重新选择。"]})
    return profiles


def replace_entries(tournament, ids):
    player_rows(ids)
    tournament.participants.all().delete()
    TournamentParticipant.objects.bulk_create([TournamentParticipant(tournament=tournament, player_id=pk) for pk in ids])


def configure_rules(tournament, values, previous_version=None, previous_pairing=None):
    try:
        tournament.oka_override = canonical_oka(tournament.oka_override)
    except ModelValidationError as exc:
        raise ValidationError({"oka_override": exc.messages}) from None
    if tournament.pairing_strategy == LEGACY:
        if {'pairing_strategy', 'ranked_table_bonuses'} & values.keys():
            raise ValidationError({'pairing_strategy': ['历史赛事沿用原规则，请创建新赛事选择自定义分桌。']})
    elif tournament.pairing_strategy not in dict(NEW_CHOICES):
        if tournament.pairing_strategy not in dict(SUPPORTED_CHOICES) or tournament.pairing_strategy != previous_pairing:
            raise ValidationError({'pairing_strategy': ['新赛事仅支持手动、完全随机或高高碰；既有瑞士轮赛事可保留原策略。']})
    try:
        tournament.ranked_table_bonuses = canonical_table_bonuses(tournament.ranked_table_bonuses)
    except ModelValidationError as exc:
        raise ValidationError({'ranked_table_bonuses': exc.messages}) from None
    if tournament.pairing_strategy != RANKED and any(value != '0' for value in tournament.ranked_table_bonuses):
        raise ValidationError({'ranked_table_bonuses': ['只有高高碰支持各桌附加基础分。']})
    # Only an explicit draft edit upgrades a legacy rule. Starting or reading a
    # legacy tournament must never silently change its version or interpretation.
    if "oka_override" in values and tournament.oka_override is not None and tournament.rules_version == 1 and "rules_version" not in values:
        tournament.rules_version = 2
    if previous_version is None:
        tournament.rules_source = f"created_v{tournament.rules_version}"
    elif tournament.rules_version != previous_version:
        tournament.rules_source = f"draft_configured_v{tournament.rules_version}"
    rules(tournament)


def create_tournament(user, values):
    if values.get('competition_type') == 'team':
        from .team_services import create_team_tournament
        return create_team_tournament(user, values)
    values = dict(values)
    ids = values.pop("participant_ids", [])
    try:
        with transaction.atomic():
            tournament = Tournament(created_by=user, **values)
            configure_rules(tournament, values)
            tournament.save()
            replace_entries(tournament, ids)
            return tournament
    except OperationalError as exc:
        database_busy(exc)


def database_busy(exc):
    if connection.vendor == "sqlite" and "locked" in str(exc).lower():
        raise TournamentConflict("赛事正在被其他请求更新，请刷新后重试。", "tournament_busy") from None
    raise exc


def mutate_tournament(pk, *, values=None, participant_ids=None, start=False, revision=None, actor=None):
    try:
        with transaction.atomic():
            # FIRST database statement is a conditional write, not a read. All
            # public mutations acquire the same parent lock, including list edits.
            # SQLite serializes writers; PostgreSQL locks this row until commit.
            # An optional client revision is compared inside this same UPDATE.
            changed = Tournament.objects.filter(pk=pk, status="draft", **({} if revision is None else {"revision": revision})).update(revision=F("revision") + 1)
            tournament = get_object_or_404(Tournament, pk=pk)
            if tournament.competition_type != 'individual':
                raise TournamentConflict('请通过团队赛入口维护阵容和启动赛事。', 'competition_mode_mismatch')
            if not changed:
                if tournament.status == "draft":
                    raise TournamentConflict("赛事草稿已被他人修改，请刷新后再保存。", "stale_tournament")
                raise TournamentConflict("赛事已经启动，不能重复启动。" if start else "赛事已启动，配置和名单已冻结。", "already_started" if start else "tournament_frozen")
            previous_version = tournament.rules_version
            previous_pairing = tournament.pairing_strategy
            if values is not None:
                for key, value in values.items():
                    setattr(tournament, key, value)
            configure_rules(tournament, values or {}, previous_version, previous_pairing)
            if participant_ids is not None:
                replace_entries(tournament, participant_ids)
            if start:
                try:
                    tournament.uma = canonical_uma(tournament.uma)
                    tournament.full_clean()
                except ModelValidationError as exc:
                    raise ValidationError(getattr(exc, "message_dict", {"uma": exc.messages})) from None
                entries = list(tournament.participants.all())
                if len(entries) not in (4, 8, 12, 16):
                    raise ValidationError({"participant_ids": ["启动需要4、8、12或16名选手。"]})
                profiles = {row.pk: row for row in player_rows([entry.player_id for entry in entries])}
                for entry in entries:
                    entry.display_name_snapshot = profiles[entry.player_id].nickname
                TournamentParticipant.objects.bulk_update(entries, ["display_name_snapshot"])
                tournament.status = "started"
                tournament.started_at = timezone.now()
            tournament.save()
            return tournament
    except OperationalError as exc:
        database_busy(exc)
