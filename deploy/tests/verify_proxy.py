"""Real multi-client proxy/limit tests on isolated loopback Docker QA only.

No production URL, credentials or seed data are accepted. Temporary clients have
different TCP source addresses. Failure logs and all service/database volumes
remain; only this script's disposable client containers are stopped.
"""
import argparse
import json
from pathlib import Path
import secrets
import subprocess

from qa_support import load_qa


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    env_file, values = load_qa(args.env_file, root)
    work = Path(args.work_dir).resolve()
    if not work.is_relative_to(root / ".verification"):
        raise ValueError("QA evidence must remain in ignored .verification")
    logs = work / "proxy"
    logs.mkdir(parents=True, exist_ok=True)
    compose = ["docker", "compose", "--env-file", str(env_file), "-f", str(root / "deploy/compose.yaml")]
    clients = []
    outcomes = {}

    def invoke(label, command, expected=(0,)):
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
        (logs / f"{label}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode not in expected:
            raise RuntimeError(f"{label} failed ({result.returncode}); see retained QA log")
        return result

    caddy_id = invoke("caddy-id", compose + ["ps", "-q", "caddy"]).stdout.strip()
    image = json.loads(invoke("caddy-image", ["docker", "inspect", "--format", "{{json .Config.Image}}", caddy_id]).stdout)
    ca = work / "proxy-root.crt"
    ca.write_text(invoke("qa-root", compose + ["exec", "-T", "caddy", "cat", "/data/caddy/pki/authorities/local/root.crt"]).stdout, encoding="utf-8")

    def new_client(label, network):
        name = values["COMPOSE_PROJECT_NAME"] + "-" + label + "-" + secrets.token_hex(3)
        invoke("start-" + label, ["docker", "run", "--rm", "-d", "--name", name,
            "--network", values["COMPOSE_PROJECT_NAME"] + "_" + network,
            "--user", "10001:10001", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true", "--tmpfs", "/tmp:rw,noexec,nosuid,size=4m",
            "--mount", f"type=bind,source={ca},target=/qa-root.crt,readonly", image, "sleep", "300"])
        clients.append(name)
        info = json.loads(invoke("inspect-" + label, ["docker", "inspect", name]).stdout)[0]
        address = info["NetworkSettings"]["Networks"][values["COMPOSE_PROJECT_NAME"] + "_" + network]["IPAddress"]
        return name, address

    def request(label, client, path="/api/v1/health/", headers=(), login=False, direct=False):
        command = ["docker", "exec", client, "curl", "--silent", "--show-error", "--max-time", "10", "--noproxy", "*",
            "--write-out", "\n%{http_code}"]
        if direct:
            command += ["--header", "Host: localhost", "http://nginx:8080" + path]
        else:
            command += ["--cacert", "/qa-root.crt", "--connect-to", "localhost:443:caddy:443", "https://localhost" + path]
        for header in headers:
            command += ["--header", header]
        if login:
            command += ["--header", "Content-Type: application/json", "--data", "{}"]
        result = invoke(label, command, (0, 52) if direct else (0,))
        body, _, code = result.stdout.rpartition("\n")
        return int(code), body

    try:
        client_a, ip_a = new_client("client-a", "edge")
        client_b, ip_b = new_client("client-b", "edge")
        attacker, _ = new_client("untrusted", "proxy")
        assert ip_a != ip_b
        spoof_headers = (
            "X-Forwarded-Proto: http", "X-Forwarded-For: 198.51.100.77, 203.0.113.19",
            "X-Forwarded-Host: evil.invalid", "X-Real-IP: 198.51.100.88",
            "Forwarded: for=198.51.100.99;proto=http;host=evil.invalid",
            "X-Forwarded-SSL: off", "X-Forwarded-Protocol: http",
        )
        assert request("spoof-all-public", client_a, headers=spoof_headers)[0] == 200
        assert request("spoof-duplicate-proto", client_a,
                       headers=("X-Forwarded-Proto: http", "X-Forwarded-Proto: https"))[0] == 200
        assert request("spoof-malformed-proto", client_a,
                       headers=("X-Forwarded-Proto: http, https",))[0] == 200
        assert request("unknown-host", client_a, headers=("Host: evil.invalid",))[0] in (400, 404, 421)
        # The internal attacker's forwarded claims do not make its original TCP
        # peer trusted. Nginx 444 closes the connection (curl code 52/HTTP 000).
        assert request("untrusted-peer", attacker, direct=True,
                       headers=("X-Forwarded-Proto: https", f"X-Forwarded-For: {values['CADDY_PROXY_IP']}"))[0] == 0
        outcomes["public_spoof_headers_and_untrusted_peer"] = "PASS"
        statuses = []
        for i in range(8):
            statuses.append(request(f"client-a-login-{i}", client_a, "/api/v1/auth/login/",
                headers=(f"X-Forwarded-For: 198.51.100.{i+1}",), login=True)[0])
        assert 403 in statuses and 429 in statuses, statuses
        # A fresh real TCP client is independent, despite the shared Caddy hop.
        assert request("client-b-not-limited", client_b, "/api/v1/auth/login/", login=True)[0] == 403
        outcomes["real_client_rate_limit_isolation"] = "PASS"
        nginx_log = invoke("nginx-access", compose + ["logs", "--no-color", "nginx"]).stdout
        assert f"{ip_a} POST /api/v1/auth/login/ 429" in nginx_log
        assert f"{ip_b} POST /api/v1/auth/login/ 403" in nginx_log
        assert "198.51.100.77 GET /api/v1/health/" not in nginx_log
        outcomes["nginx_real_client_log"] = "PASS"
        print(json.dumps({"result": "PASS", "checks": outcomes}, ensure_ascii=False, indent=2))
    finally:
        for client in clients:
            # Client names are generated above and never target service containers.
            invoke("stop-" + client, ["docker", "stop", "--time", "1", client])


if __name__ == "__main__":
    main()
