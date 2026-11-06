"""Create a fresh, ignored loopback QA environment. Never reads Owner settings."""
import secrets
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[2]
    name = "docker-qa-" + secrets.token_hex(4)
    directory = root / ".verification" / name
    directory.mkdir(parents=True, mode=0o700)
    # A separate subnet per QA project avoids sharing a trusted proxy identity.
    # Production preflight performs the full host/network collision check.
    network_octet = secrets.randbelow(200) + 20
    values = {
        "COMPOSE_PROJECT_NAME": "riichi-" + name,
        "RIICHI_VERSION": name, "SERVER_NAME": "localhost",
        "CSRF_TRUSTED_ORIGINS": "https://localhost:18443",
        "SECRET_KEY": secrets.token_urlsafe(64), "POSTGRES_DB": "riichi_qa",
        "POSTGRES_PASSWORD": secrets.token_hex(32),
        "POSTGRES_ADMIN_PASSWORD": secrets.token_hex(32),
        "PUBLIC_BIND_IP": "127.0.0.1", "CADDY_CONFIG": "Caddyfile.qa",
        "PROXY_SUBNET": f"172.30.{network_octet}.0/28",
        "CADDY_PROXY_IP": f"172.30.{network_octet}.2",
        "HTTP_PORT": "18080", "HTTPS_PORT": "18443",
    }
    lines = (root / "deploy/.env.example").read_text().splitlines()
    environment = directory / ".env"
    environment.write_text("\n".join(key + "=" + values[key] if (key := line.partition("=")[0]) in values else line for line in lines) + "\n", encoding="utf-8", newline="\n")
    environment.chmod(0o600)
    print(f"QA prepared: {directory.relative_to(root).as_posix()}")
    print("Set RIICHI_ENV_FILE to that directory's .env; ports 18080/18443 must be free.")
    print("After startup, export Caddy /data/caddy/pki/authorities/local/root.crt for QA client trust.")


if __name__ == "__main__":
    main()
