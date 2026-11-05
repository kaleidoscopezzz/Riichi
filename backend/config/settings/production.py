"""HTTPS production behind the private Compose Nginx, never a public API port."""
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

if DEBUG:  # noqa: F405
    raise ImproperlyConfigured("Production requires DEBUG=False.")
if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("Production requires explicit ALLOWED_HOSTS.")
if any(host.startswith(".") for host in ALLOWED_HOSTS):  # noqa: F405
    raise ImproperlyConfigured("Production requires explicit ALLOWED_HOSTS, without subdomain wildcards.")

# Discrete parameters avoid embedding/URL-encoding a password in DATABASE_URL.
# Existing explicit DATABASE_URL users continue to work unchanged.
if env("POSTGRES_DB", default=""):  # noqa: F405
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"), "USER": env("POSTGRES_USER"),  # noqa: F405
        "PASSWORD": env("POSTGRES_PASSWORD"),  # noqa: F405
        "HOST": env("POSTGRES_HOST", default="db"),  # noqa: F405
        "PORT": env.int("POSTGRES_PORT", default=5432),  # noqa: F405
    }}
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":  # noqa: F405
    raise ImproperlyConfigured("Production requires a PostgreSQL DATABASE_URL.")
if any(not origin.startswith("https://") for origin in CORS_ALLOWED_ORIGINS):  # noqa: F405
    raise ImproperlyConfigured("Production CORS origins must use HTTPS.")
for origin in CSRF_TRUSTED_ORIGINS:  # noqa: F405
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname or "*" in origin or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise ImproperlyConfigured("Production CSRF origins must be explicit HTTPS origins without a path.")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# Only enable when the API is unreachable from the Internet and the proxy
# overwrites X-Forwarded-Proto. The shipped Compose topology enforces both.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if env.bool("TRUST_PROXY_HEADERS", default=False) else None  # noqa: F405
USE_X_FORWARDED_HOST = False
SECURE_HSTS_SECONDS = env.int("HSTS_SECONDS", default=0)  # noqa: F405
if SECURE_HSTS_SECONDS < 0:
    raise ImproperlyConfigured("HSTS_SECONDS must be non-negative.")
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=28800)  # noqa: F405
if SESSION_COOKIE_AGE <= 0:
    raise ImproperlyConfigured("SESSION_COOKIE_AGE must be positive.")
SESSION_SAVE_EVERY_REQUEST = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)  # noqa: F405
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True  # noqa: F405
LOGGING = {
    "version": 1, "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django": {"handlers": ["console"], "level": "INFO", "propagate": False}},
}
