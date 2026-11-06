from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied


class CsrfFailed(PermissionDenied):
    default_detail = "安全校验失败，请刷新页面后重试。"
    default_code = "csrf_failed"


class CsrfSessionAuthentication(SessionAuthentication):
    """Same Session/CSRF policy as DRF; the failure matches csrf_failure and never echoes Origin/Referer."""

    def enforce_csrf(self, request):
        try:
            super().enforce_csrf(request)
        except PermissionDenied:
            raise CsrfFailed() from None
