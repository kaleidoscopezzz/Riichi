"""Create a fresh, ignored loopback QA environment. Never reads Owner settings."""
import secrets
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[2]
    name = "docker-qa-" + secrets.token_hex(4)
    directory = root / ".verification" / name
    directory.mkdir(parents=True, mode=0o700)
    certs = directory / "certs"
    # Bind-mount root must be traversable by container UID 101. The host's QA
    # parent remains 0700, so other host users cannot reach the private key.
    certs.mkdir(mode=0o755)
    values = {
        "COMPOSE_PROJECT_NAME": "riichi-" + name,
        "RIICHI_VERSION": name, "SERVER_NAME": "localhost",
        "CSRF_TRUSTED_ORIGINS": "https://localhost:18443",
        "SECRET_KEY": secrets.token_urlsafe(64), "POSTGRES_DB": "riichi_qa",
        "POSTGRES_PASSWORD": secrets.token_hex(32),
        "POSTGRES_ADMIN_PASSWORD": secrets.token_hex(32),
        "TLS_CERT_DIR": str(certs), "PUBLIC_BIND_IP": "127.0.0.1",
        "HTTP_PORT": "18080", "HTTPS_PORT": "18443",
    }
    lines = (root / "deploy/.env.example").read_text().splitlines()
    environment = directory / ".env"
    environment.write_text("\n".join(key + "=" + values[key] if (key := line.partition("=")[0]) in values else line for line in lines) + "\n")
    environment.chmod(0o600)
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-days", "2", "-nodes", "-keyout", str(certs / "privkey.pem"), "-out", str(certs / "fullchain.pem"), "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], check=True, capture_output=True)
    # QA-only key in a 0700 parent; the non-root container needs read access.
    (certs / "privkey.pem").chmod(0o644)
    print(f"QA prepared: {directory.relative_to(root)}")
    print("Set RIICHI_ENV_FILE to that directory's .env; ports 18080/18443 must be free.")


if __name__ == "__main__":
    main()
