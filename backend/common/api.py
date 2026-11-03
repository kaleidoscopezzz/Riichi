from django.http import JsonResponse
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler


def error_response(code, message, fields=None, status=400):
    return JsonResponse({"error": {"code": code, "message": message, "fields": fields or {}}}, status=status)


def csrf_failure(request, reason=""):
    # Do not expose the token or internal rejection reason.
    return error_response("csrf_failed", "安全校验失败，请刷新页面后重试。", status=403)


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        code = getattr(exc, "default_code", "request_failed")
        fields = response.data if isinstance(exc, ValidationError) else {}
        message = "输入信息有误，请检查表单。" if fields else str(getattr(exc, "detail", "请求失败。"))
        response.data = {"error": {"code": code, "message": message, "fields": fields}}
    return response


class StrictFieldsMixin:
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise ValidationError({"non_field_errors": ["请求必须是 JSON 对象。"]})
        unknown = set(data) - set(self.fields)
        if unknown:
            raise ValidationError({key: ["不允许提供此字段。"] for key in sorted(unknown)})
        return super().to_internal_value(data)
