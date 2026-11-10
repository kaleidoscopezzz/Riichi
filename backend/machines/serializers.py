import re

from rest_framework import serializers
from common.api import StrictFieldsMixin
from .models import MahjongMachine


class MachineSerializer(serializers.ModelSerializer):
    class Meta:
        model = MahjongMachine
        fields = ["id", "machine_no", "name", "location", "status", "description", "created_at", "updated_at"]


class MachineWriteSerializer(StrictFieldsMixin, serializers.Serializer):
    machine_no = serializers.CharField(max_length=3, required=False)
    name = serializers.CharField(max_length=100)
    location = serializers.CharField(max_length=200, allow_blank=True, required=False)
    description = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    status = serializers.ChoiceField(choices=["available", "maintenance", "disabled"], required=False)

    def validate_machine_no(self, value):
        if not re.fullmatch(r"[0-9]{1,3}", value):
            raise serializers.ValidationError("设备编号必须为 1～3 位数字，保存时统一为三位。")
        return value.zfill(3)
