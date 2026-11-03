from .api import error_response


class ApiErrorMiddleware:
    """Keep router and Django errors JSON without exposing debug HTML to clients."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/") and response.status_code >= 400 and not response.get("Content-Type", "").startswith("application/json"):
            return error_response("not_found" if response.status_code == 404 else "request_failed", "接口不存在。" if response.status_code == 404 else "请求未能完成。", status=response.status_code)
        return response
