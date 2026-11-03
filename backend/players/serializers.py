from rest_framework import serializers
from common.api import StrictFieldsMixin
from .models import PlayerProfile


class ProfileUpdateSerializer(StrictFieldsMixin, serializers.Serializer):
    nickname = serializers.CharField(max_length=80)


class PlayerSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    date_joined = serializers.DateTimeField(source="user.date_joined", read_only=True)

    class Meta:
        model = PlayerProfile
        fields = ["id", "username", "nickname", "date_joined", "created_at", "updated_at"]
