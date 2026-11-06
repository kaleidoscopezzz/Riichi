import unicodedata

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404, JsonResponse
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler

# LRM/RLM, embeddings/overrides and isolates can visually disguise a name.
BIDI_CONTROLS = frozenset("\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


def error_response(code, message, fields=None, status=400):
    return JsonResponse({"error": {"code": code, "message": message, "fields": fields or {}}}, status=status)


def csrf_failure(request, reason=""):
    # Do not expose the token or internal rejection reason.
    return error_response("csrf_failed", "安全校验失败，请刷新页面后重试。", status=403)


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        # Django's own exceptions carry no API code; never echo their internal text.
        if isinstance(exc, Http404):
            code, message, fields = "not_found", "请求的资源不存在。", {}
        elif isinstance(exc, DjangoPermissionDenied):
            code, message, fields = "permission_denied", "您没有执行该操作的权限。", {}
        else:
            code = getattr(exc, "default_code", "request_failed")
            fields = response.data if isinstance(exc, ValidationError) else {}
            message = "输入信息有误，请检查表单。" if fields else str(getattr(exc, "detail", "请求失败。"))
        response.data = {"error": {"code": code, "message": message, "fields": fields}}
    return response


def search_text(value):
    """PostgreSQL text cannot hold NUL; reject every Cc control before querying."""
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise ValidationError({"search": ["搜索内容包含无效字符。"]})
    return value


def validate_display_name(value):
    """Names must be visible: no Cc/bidi controls, at least one L/N/P/S character (emoji ZWJ allowed)."""
    if any(unicodedata.category(char) == "Cc" or char in BIDI_CONTROLS for char in value):
        raise ValidationError("名称不能包含控制字符或文字方向控制符。")
    if not any(unicodedata.category(char)[0] in "LNPS" for char in value):
        raise ValidationError("名称至少需要包含一个可见的文字、数字、标点或符号。")
    return value


class StrictFieldsMixin:
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise ValidationError({"non_field_errors": ["请求必须是 JSON 对象。"]})
        unknown = set(data) - set(self.fields)
        if unknown:
            raise ValidationError({key: ["不允许提供此字段。"] for key in sorted(unknown)})
        return super().to_internal_value(data)
