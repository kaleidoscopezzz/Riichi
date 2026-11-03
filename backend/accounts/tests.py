from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, Client
from players.models import PlayerProfile

User = get_user_model()


class AccountFlowTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.token = self.client.get("/api/v1/auth/csrf/").json()["data"]["csrf_token"]
        # Test-only password. No fixture accounts or default production credential.
        self.payload = dict(username="testplayer", nickname="测试选手", password="Test-Only!39xM", password_confirm="Test-Only!39xM")

    def write(self, path, data, method="post", token=None):
        return getattr(self.client, method)("/api/v1/" + path, data, content_type="application/json", HTTP_X_CSRFTOKEN=token or self.token)

    def register(self):
        return self.write("auth/register/", self.payload)

    def sign_in(self):
        self.register()
        response = self.write("auth/login/", {"username": self.payload["username"], "password": self.payload["password"]})
        self.token = self.client.get("/api/v1/auth/csrf/").json()["data"]["csrf_token"]
        return response

    def test_register_profile_hash_and_permissions(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="testplayer")
        self.assertTrue(user.check_password(self.payload["password"]))
        self.assertNotEqual(user.password, self.payload["password"])
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(user.player_profile.nickname, "测试选手")
        self.assertNotIn("password", str(response.json()))

    def test_duplicate_username(self):
        self.register()
        self.assertEqual(self.register().status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_password_validation_and_confirmation(self):
        for changes in [{"password_confirm": "different"}, {"password": "12345678", "password_confirm": "12345678"}, {"password": "short", "password_confirm": "short"}]:
            with self.subTest(changes=list(changes)):
                self.assertEqual(self.write("auth/register/", self.payload | changes).status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    def test_strict_registration_fields(self):
        for field in ["is_staff", "is_superuser", "is_active", "id", "groups"]:
            self.assertEqual(self.write("auth/register/", self.payload | {field: True}).status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    def test_registration_atomic_on_profile_failure(self):
        with patch("players.signals.PlayerProfile.objects.create", side_effect=IntegrityError):
            self.assertEqual(self.register().status_code, 409)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(PlayerProfile.objects.count(), 0)

    def test_profile_unique_constraint(self):
        self.register()
        with self.assertRaises(IntegrityError), transaction.atomic():
            PlayerProfile.objects.create(user=User.objects.get(), nickname="重复")

    def test_login_restore_logout(self):
        self.assertEqual(self.sign_in().status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)
        restored = Client(enforce_csrf_checks=True)
        restored.cookies = self.client.cookies.copy()
        self.assertEqual(restored.get("/api/v1/auth/me/").status_code, 200)
        self.assertEqual(self.write("auth/logout/", {}).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 403)
        self.assertEqual(restored.get("/api/v1/auth/me/").status_code, 403)

    def test_login_failure_and_inactive(self):
        self.register()
        self.assertEqual(self.write("auth/login/", {"username": "testplayer", "password": "wrong"}).status_code, 400)
        User.objects.update(is_active=False)
        self.assertEqual(self.write("auth/login/", {"username": "testplayer", "password": self.payload["password"]}).status_code, 400)

    def test_anonymous_denied_health_public(self):
        for path in ["auth/me/", "players/me/", "players/"]:
            self.assertEqual(self.client.get("/api/v1/" + path).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/health/").status_code, 200)

    def test_anonymous_csrf_required_for_register_and_login(self):
        for path in ["register", "login"]:
            for headers in [{}, {"HTTP_X_CSRFTOKEN": "invalid"}]:
                response = self.client.post(f"/api/v1/auth/{path}/", self.payload, content_type="application/json", **headers)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["error"]["code"], "csrf_failed")
        self.assertEqual(User.objects.count(), 0)

    def test_authenticated_writes_need_csrf_and_trusted_origin(self):
        self.sign_in()
        for path, method, payload in [("auth/logout/", "post", {}), ("players/me/", "patch", {"nickname": "新昵称"})]:
            self.assertEqual(getattr(self.client, method)("/api/v1/" + path, payload, content_type="application/json").status_code, 403)
            self.assertEqual(self.write(path, payload, method, token="invalid").status_code, 403)
        self.assertEqual(self.client.patch("/api/v1/players/me/", {"nickname": "危险"}, content_type="application/json", HTTP_X_CSRFTOKEN=self.token, HTTP_ORIGIN="https://untrusted.example").status_code, 403)

    def test_own_profile_only(self):
        self.sign_in()
        other = User.objects.create_user(username="otherplayer", password="Test-Only!Other39")
        self.assertEqual(self.write("players/me/", {"nickname": "新的昵称"}, "patch").status_code, 200)
        self.assertEqual(self.write("players/me/", {"nickname": "偷改", "user": other.pk}, "patch").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/v1/players/{other.player_profile.pk}/", {}, content_type="application/json", HTTP_X_CSRFTOKEN=self.token).status_code, 404)
        other.player_profile.refresh_from_db()
        self.assertEqual(other.player_profile.nickname, "otherplayer")
        for value in ["", " " * 4, "长" * 81]:
            self.assertEqual(self.write("players/me/", {"nickname": value}, "patch").status_code, 400)

    def test_admin_list_permissions_search_and_pagination(self):
        self.sign_in()
        self.assertEqual(self.client.get("/api/v1/players/").status_code, 403)
        User.objects.filter(username="testplayer").update(is_staff=True)
        for number in range(21):
            User.objects.create_user(username=f"member{number}")
        response = self.client.get("/api/v1/players/").json()["data"]
        self.assertEqual(response["count"], 22)
        self.assertEqual(len(response["results"]), 20)
        self.assertIsNotNone(response["next"])
        self.assertEqual(set(response["results"][0]), {"id", "username", "nickname", "date_joined", "created_at", "updated_at"})
        for search in ["测试选手", "testplayer"]:
            result = self.client.get("/api/v1/players/", {"search": search}).json()["data"]
            self.assertEqual(result["count"], 1)

    def test_input_shape_and_method_errors(self):
        for value in [[], None, "bad"]:
            self.assertEqual(self.write("auth/register/", value).status_code, 400)
        self.assertEqual(self.client.get("/api/v1/auth/login/").status_code, 405)
        self.assertEqual(self.client.get("/api/v1/missing/").json()["error"]["code"], "not_found")
