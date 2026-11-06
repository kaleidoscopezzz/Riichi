"""Shared fail-closed protection for destructive/seed Docker QA helpers."""
from pathlib import Path
import os
from urllib.parse import urlsplit


def load_qa(env_file, root, url=None):
    path = Path(env_file).resolve()
    if not path.is_relative_to(root / ".verification") or not path.is_file():
        raise ValueError("QA settings must be an existing file in ignored .verification")
    values = dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                  if line and not line.startswith("#"))
    required = {
        "POSTGRES_DB": "riichi_qa", "SERVER_NAME": "localhost",
        "PUBLIC_BIND_IP": "127.0.0.1", "CADDY_CONFIG": "Caddyfile.qa",
    }
    if any(values.get(key) != value for key, value in required.items()):
        raise ValueError("Fresh loopback riichi_qa / Caddyfile.qa configuration required")
    if not values.get("COMPOSE_PROJECT_NAME", "").startswith("riichi-docker-qa-"):
        raise ValueError("Dedicated riichi-docker-qa project required")
    # Compose gives the invoking shell precedence over --env-file. Fail closed
    # instead of allowing inherited production variables to redirect a QA run.
    identity_keys = (*required, "COMPOSE_PROJECT_NAME", "PROXY_SUBNET", "PROXY_DYNAMIC_RANGE", "CADDY_PROXY_IP", "HTTP_PORT", "HTTPS_PORT")
    if any(key in os.environ and os.environ[key] != values.get(key) for key in identity_keys):
        raise ValueError("Inherited environment overrides the isolated QA target")
    if url:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname != "localhost"
                or parsed.port != int(values["HTTPS_PORT"]) or parsed.path
                or parsed.query or parsed.fragment or parsed.username or parsed.password):
            raise ValueError("QA URL must exactly match the configured HTTPS loopback origin")
    return path, values
