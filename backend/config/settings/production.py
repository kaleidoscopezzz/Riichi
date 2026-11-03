"""Secure production defaults; deployment infrastructure remains a future task."""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

if DEBUG:  # noqa: F405
    raise ImproperlyConfigured("Production requires DEBUG=False.")
if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("Production requires explicit ALLOWED_HOSTS.")
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":  # noqa: F405
    raise ImproperlyConfigured("Production requires a PostgreSQL DATABASE_URL.")
if any(not origin.startswith("https://") for origin in CORS_ALLOWED_ORIGINS):  # noqa: F405
    raise ImproperlyConfigured("Production CORS origins must use HTTPS.")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
