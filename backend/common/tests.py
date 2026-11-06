import json
from django.test import TestCase, override_settings
from django.urls import reverse


class HealthTests(TestCase):
    def test_health_contract_without_database_access(self):
        with self.assertNumQueries(0):
            response = self.client.get(reverse("common:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "riichi-api", "api_version": "v1"})
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_health_is_read_only(self):
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(reverse("common:health")).status_code, 405)

    @override_settings(CORS_ALLOWED_ORIGINS=["http://localhost:5173", "http://127.0.0.1:5173"])
    def test_local_frontend_cors(self):
        for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
            with self.subTest(origin=origin):
                response = self.client.get(reverse("common:health"), HTTP_ORIGIN=origin)
                self.assertEqual(response["Access-Control-Allow-Origin"], origin)
                self.assertNotIn("Access-Control-Allow-Credentials", response)

    def test_untrusted_origin_has_no_cors_access(self):
        response = self.client.get(reverse("common:health"), HTTP_ORIGIN="https://untrusted.example")
        self.assertNotIn("Access-Control-Allow-Origin", response)

    @override_settings(CORS_ALLOWED_ORIGINS=["http://localhost:5173"])
    def test_preflight(self):
        response = self.client.options(reverse("common:health"), HTTP_ORIGIN="http://localhost:5173", HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:5173")

    def test_head_has_no_body(self):
        response = self.client.head(reverse("common:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")

    @override_settings(ALLOWED_HOSTS=["localhost", "127.0.0.1"])
    def test_untrusted_host_rejected(self):
        response = self.client.get(reverse("common:health"), HTTP_HOST="untrusted.example")
        self.assertEqual(response.status_code, 400)


class ErrorContractTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.test import Client
        self.admin = get_user_model().objects.create_user(username="contract_admin", is_staff=True)
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.admin)

    def test_unknown_api_route_keeps_security_headers(self):
        response = self.client.get("/api/nonexistent/")
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (404, "not_found"))
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn(response.get("Content-Length", str(len(response.content))), (str(len(response.content)),))  # never a stale HTML length

    def test_middleware_copies_headers_and_cookies_but_not_body_type(self):
        from django.http import HttpResponse
        from django.test import RequestFactory
        from .middleware import ApiErrorMiddleware
        def inner(request):
            response = HttpResponse("<h1>Server Error</h1>", status=500, content_type="text/html")
            response["Vary"] = "Cookie"
            response.set_cookie("csrftoken", "rotated", samesite="Lax")
            return response
        response = ApiErrorMiddleware(inner)(RequestFactory().get("/api/v1/broken/"))
        self.assertEqual((response.status_code, json.loads(response.content)["error"]["code"]), (500, "request_failed"))
        self.assertEqual((response["Content-Type"], response["Vary"]), ("application/json", "Cookie"))
        self.assertEqual((response.cookies["csrftoken"].value, response.cookies["csrftoken"]["samesite"]), ("rotated", "Lax"))
        self.assertNotIn(b"Server Error", response.content)

    def test_drf_csrf_failure_matches_django_csrf_failure(self):
        for headers in ({}, {"HTTP_X_CSRFTOKEN": "invalid"}, {"HTTP_ORIGIN": "https://untrusted.example"}):
            with self.subTest(headers=sorted(headers)):
                response = self.client.post("/api/v1/tournaments/", {"name": "拒绝", "round_count": 1}, content_type="application/json", **headers)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {"error": {"code": "csrf_failed", "message": "安全校验失败，请刷新页面后重试。", "fields": {}}})
                self.assertNotIn(b"untrusted", response.content)
                self.assertNotIn(b"CSRF Failed", response.content)
        # Anonymous requests remain not_authenticated (the only code the frontend special-cases).
        from django.test import Client
        self.assertEqual(Client(enforce_csrf_checks=True).post("/api/v1/tournaments/", {}, content_type="application/json").json()["error"]["code"], "not_authenticated")

    def test_get_object_or_404_and_django_permission_denied_codes(self):
        for path in ("/api/v1/tournaments/999999/", "/api/v1/players/999999/", "/api/v1/machines/999999/", "/api/v1/round-tables/999999/result/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {"error": {"code": "not_found", "message": "请求的资源不存在。", "fields": {}}})
        from django.core.exceptions import PermissionDenied
        from .api import api_exception_handler
        response = api_exception_handler(PermissionDenied("internal detail"), {})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data, {"error": {"code": "permission_denied", "message": "您没有执行该操作的权限。", "fields": {}}})
