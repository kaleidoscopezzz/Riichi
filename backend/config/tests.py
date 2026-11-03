"""Configuration boundaries tested in clean imports, without a database server."""
import os
from pathlib import Path
import secrets
import subprocess
import sys

from django.test import SimpleTestCase


class ProductionConfigurationTests(SimpleTestCase):
    def import_production(self, **overrides):
        environment = os.environ.copy()
        environment.update({
            "SECRET_KEY": secrets.token_urlsafe(64),
            "DEBUG": "False",
            "ALLOWED_HOSTS": "riichi.example",
            "DATABASE_URL": "postgresql://localhost/riichi",
            "CORS_ALLOWED_ORIGINS": "https://riichi.example",
            **overrides,
        })
        return subprocess.run(
            [sys.executable, "-c", "import config.settings.production"],
            cwd=Path(__file__).resolve().parent.parent,
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def assert_rejected(self, expected_message, **overrides):
        result = self.import_production(**overrides)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(expected_message, result.stderr)

    def test_explicit_secure_configuration_imports(self):
        result = self.import_production()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_or_weak_secret_rejected(self):
        for secret in ("", "short", "a" * 64):
            with self.subTest(kind="empty" if not secret else "weak"):
                self.assert_rejected("SECRET_KEY must be", SECRET_KEY=secret)

    def test_debug_rejected(self):
        self.assert_rejected("DEBUG=False", DEBUG="True")

    def test_missing_hosts_rejected(self):
        self.assert_rejected("explicit ALLOWED_HOSTS", ALLOWED_HOSTS="")

    def test_wildcard_hosts_rejected(self):
        self.assert_rejected("wildcard access", ALLOWED_HOSTS="*")

    def test_sqlite_rejected(self):
        self.assert_rejected("PostgreSQL DATABASE_URL", DATABASE_URL="sqlite:///db.sqlite3")

    def test_wildcard_cors_rejected(self):
        self.assert_rejected("explicit http(s) origins", CORS_ALLOWED_ORIGINS="*")

    def test_plain_http_cors_rejected(self):
        self.assert_rejected("must use HTTPS", CORS_ALLOWED_ORIGINS="http://riichi.example")
