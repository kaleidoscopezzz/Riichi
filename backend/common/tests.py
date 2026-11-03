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
