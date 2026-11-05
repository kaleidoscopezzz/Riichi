"""Full test suite on an explicitly isolated PostgreSQL DB, with local HTTP tests.

Use ONLY with deploy/tests/compose.qa.yaml. Django needs CREATEDB for its test DB;
the production application role intentionally does not have that privilege.
"""
from django.core.exceptions import ImproperlyConfigured
from config.settings.local import *  # noqa: F403

if env("POSTGRES_DB") != "riichi_qa":  # noqa: F405
    raise ImproperlyConfigured("PostgreSQL tests require isolated riichi_qa.")
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": "riichi_qa",
    "USER": env("POSTGRES_USER"), "PASSWORD": env("POSTGRES_PASSWORD"),  # noqa: F405
    "HOST": "db", "PORT": 5432,
    "TEST": {"NAME": "test_riichi_qa"},
}}
