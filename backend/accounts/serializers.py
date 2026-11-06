from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from common.api import StrictFieldsMixin, validate_display_name

User = get_user_model()


class RegisterSerializer(StrictFieldsMixin, serializers.Serializer):
    username = serializers.CharField(max_length=150, validators=User._meta.get_field("username").validators)
    nickname = serializers.CharField(max_length=80, validators=[validate_display_name])
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("此用户名已被使用。")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": ["两次输入的密码不一致。"]})
        try:
            validate_password(attrs["password"], User(username=attrs["username"]))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages})
        return attrs


class LoginSerializer(StrictFieldsMixin, serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(trim_whitespace=False, max_length=128, write_only=True)


def user_data(user):
    return {"id": user.pk, "username": user.username, "is_staff": user.is_staff, "date_joined": user.date_joined.isoformat()}
