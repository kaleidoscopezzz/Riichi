from rest_framework import serializers
from common.api import StrictFieldsMixin, validate_display_name
from .models import PlayerProfile


class ProfileUpdateSerializer(StrictFieldsMixin, serializers.Serializer):
    # Shared by player nicknames and the administrator's own display name (players/me).
    nickname = serializers.CharField(max_length=80, validators=[validate_display_name])


class PlayerSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    reference_count = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()

    class Meta:
        model = PlayerProfile
        fields = ["id", "nickname", "is_active", "reference_count", "can_delete", "created_at", "updated_at"]

    def get_reference_count(self, obj):
        return getattr(obj, "entry_count", None) if hasattr(obj, "entry_count") else obj.tournament_entries.count()

    def get_can_delete(self, obj):
        return not (obj.user.is_staff or obj.user.is_superuser or self.get_reference_count(obj))


class AccountProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    date_joined = serializers.DateTimeField(source="user.date_joined", read_only=True)

    class Meta:
        model = PlayerProfile
        fields = ["id", "username", "nickname", "date_joined", "created_at", "updated_at"]
