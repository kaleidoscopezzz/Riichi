import json

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.cache import never_cache
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from common.api import error_response
from .serializers import RegisterSerializer, LoginSerializer, user_data


@method_decorator([csrf_protect, never_cache, sensitive_post_parameters("password", "password_confirm")], name="dispatch")
class AuthWriteView(View):
    http_method_names = ["post", "options"]

    def http_method_not_allowed(self, request, *args, **kwargs):
        return error_response("method_not_allowed", "不支持此请求方法。", status=405)

    @sensitive_variables()
    def post(self, request):
        if request.content_type != "application/json":
            return error_response("unsupported_media_type", "请使用 application/json。", status=415)
        try:
            data = json.loads(request.body)
            return self.execute(request, data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return error_response("parse_error", "JSON 格式无效。")
        except ValidationError as exc:
            return error_response("validation_error", "输入信息有误，请检查表单。", exc.detail)


class RegisterView(AuthWriteView):
    @sensitive_variables()
    def execute(self, request, data):
        if request.user.is_authenticated:
            return error_response("already_authenticated", "请先退出当前账号。", status=409)
        serializer = RegisterSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            with transaction.atomic():
                user = get_user_model().objects.create_user(username=values["username"], password=values["password"])
                profile = user.player_profile
                profile.nickname = values["nickname"]
                profile.save(update_fields=["nickname", "updated_at"])
        except IntegrityError:
            return error_response("registration_conflict", "注册冲突，请检查用户名后重试。", status=409)
        # Registration does not implicitly sign in; login has its own CSRF-checked flow.
        return JsonResponse({"data": user_data(user)}, status=201)


class LoginView(AuthWriteView):
    @sensitive_variables()
    def execute(self, request, data):
        serializer = LoginSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request, **serializer.validated_data)
        if user is None:
            return error_response("invalid_credentials", "用户名或密码错误，或账号不可用。", status=400)
        login(request, user)
        return JsonResponse({"data": user_data(user)})


class LogoutView(AuthWriteView):
    def execute(self, request, data):
        if not isinstance(data, dict) or data:
            return error_response("validation_error", "退出请求应为空 JSON 对象。")
        if not request.user.is_authenticated:
            return error_response("not_authenticated", "请先登录。", status=403)
        logout(request)
        return JsonResponse({"data": {"logged_out": True}})


class MeView(APIView):
    def get(self, request):
        return Response({"data": user_data(request.user)}, headers={"Cache-Control": "no-store"})


@never_cache
def csrf_view(request):
    if request.method != "GET":
        return error_response("method_not_allowed", "只支持 GET。", status=405)
    return JsonResponse({"data": {"csrf_token": get_token(request)}})
