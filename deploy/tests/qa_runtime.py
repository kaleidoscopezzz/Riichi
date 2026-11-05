"""Real HTTPS QA on a NEW riichi_qa database, never an Owner database.

Usage: python3 deploy/tests/qa_runtime.py --env-file ... --ca ... --url https://localhost:18443
Creates random, temporary QA identities in memory; prints only verification data.
"""
import argparse
import http.cookiejar
import json
import secrets
import ssl
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--ca", required=True)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    assert args.url.startswith("https://localhost:"), "QA is loopback only"
    root = Path(__file__).resolve().parents[2]
    compose = ["docker", "compose", "--env-file", args.env_file, "-f", str(root / "deploy/compose.yaml")]
    username, password = "qa_" + secrets.token_hex(6), secrets.token_urlsafe(32)
    seed = '''
import json, sys
import django; django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
assert settings.DATABASES['default']['NAME'] == 'riichi_qa', 'QA database required'
U=get_user_model()
assert not U.objects.filter(is_superuser=True).exists(), 'Use a fresh QA database'
credentials=json.load(sys.stdin)
U.objects.create_superuser(username=credentials['username'],password=credentials['password'])
u=U(username='qa_nonstaff');u.set_password(credentials['password']);u.save()
'''
    subprocess.run(compose + ["exec", "-T", "api", "python", "-c", seed], input=json.dumps({"username": username, "password": password}), text=True, check=True)
    jar = http.cookiejar.CookieJar()
    client = build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=args.ca)), HTTPCookieProcessor(jar))
    count = 0

    def raw(path, method="GET", body=None, headers=None):
        request = Request(args.url + path, method=method, headers=headers or {}, data=json.dumps(body).encode() if body is not None else None)
        try:
            response = client.open(request, timeout=15)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, response.read(), response.headers

    def call(path, method="GET", body=None, expected=200, csrf=True, origin=None):
        nonlocal count
        headers = {"Content-Type": "application/json"}
        if method != "GET" and csrf:
            headers["X-CSRFToken"] = call("/auth/csrf/")["csrf_token"]
            headers["Origin"] = origin or args.url
        status, content, _ = raw("/api/v1" + path, method, body, headers)
        payload = json.loads(content)
        assert status == expected, (path, status, payload.get("error", {}).get("code"))
        count += 1
        return payload.get("data", payload)

    status, home, headers = raw("/tournaments/123")
    assert status == 200 and b'<div id="root">' in home
    assert headers["Strict-Transport-Security"] == "max-age=0"
    assert raw("/assets/missing.js")[0] == 404
    assert raw("/.env")[0] == 404
    assert call("/not-a-real-api/", expected=404)["error"]["code"] == "not_found"
    assert call("/health/")["status"] == "ok"
    # Spoofed proxy proto is overwritten by TLS Nginx; no redirect loop.
    assert raw("/api/v1/health/", headers={"X-Forwarded-Proto": "http", "X-Forwarded-Host": "evil.invalid"})[0] == 200
    call("/players/", expected=403)
    call("/auth/register/", "POST", {}, 403)
    credentials = {"username": username, "password": password}
    call("/auth/login/", "POST", credentials, 403, csrf=False)
    call("/auth/login/", "POST", credentials, 403, origin="https://evil.invalid")
    call("/auth/login/", "POST", {"username": "qa_nonstaff", "password": password}, 403)
    call("/auth/login/", "POST", credentials)
    assert any(cookie.name == "sessionid" and cookie.secure and cookie.has_nonstandard_attr("HttpOnly") for cookie in jar)
    assert any(cookie.name == "csrftoken" and cookie.secure for cookie in jar)
    assert call("/auth/me/")["username"] == username
    players = [call("/players/", "POST", {"nickname": f"Docker QA {i+1:02}"}, 201)["id"] for i in range(16)]
    for i in range(4):
        call("/machines/", "POST", {"machine_no": f"{i+1:03}", "name": f"QA物理桌{i+1}"}, 201)
    runs = []
    for size, rounds in [(4, 1), (8, 3), (12, 2), (16, 6)]:
        tournament = call("/tournaments/", "POST", {"name": f"Docker QA {size}人{rounds}轮", "round_count": rounds, "participant_ids": players[:size]}, 201)
        pk = tournament["id"]
        call(f"/tournaments/{pk}/start/", "POST", {})
        machines = [m["machine_id"] for m in call("/machine-resources/")["results"] if m["assignable"]][:size//4]
        for number in range(1, rounds+1):
            body = {"round_number": number}
            if number == 1:
                body["machine_ids"] = machines
            current = call(f"/tournaments/{pk}/rounds/", "POST", body, 201)
            for table in current["tables"]:
                # Includes negative and zero; three-way ties exercise Fraction.
                values = [-1000, 0, 50000, 51000] if size == 4 else [30000, 30000, 30000, 10000]
                points = [{"participant_id": s["participant_id"], "raw_points": value} for s, value in zip(table["seats"], values)]
                if size == 4:
                    invalid = [dict(p) for p in points]; invalid[0]["raw_points"] += 1
                    call(f'/round-tables/{table["id"]}/result/confirm/', "POST", {"version": 0, "points": invalid}, 400)
                result = call(f'/round-tables/{table["id"]}/result/confirm/', "POST", {"version": 0, "points": points})
                assert result["status"] == "confirmed"
                call(f'/round-tables/{table["id"]}/result/confirm/', "POST", {"version": result["version"], "points": points}, 409)
        workspace = call(f"/tournaments/{pk}/workspace/")
        for members in workspace["unresolved_groups"]:
            draw = call(f"/tournaments/{pk}/lotteries/", "POST", {"members": members, "order": members[::-1], "source_versions": workspace["source_versions"], "method": "隔离QA抽签模拟", "description": "Docker HTTPS 流程验证", "drawn_at": datetime.now(timezone.utc).isoformat()}, 201)
            call(f'/tournaments/{pk}/lotteries/{draw["id"]}/confirm/', "POST", {"confirmed": True})
        final = call(f"/tournaments/{pk}/complete/", "POST", {"confirmed": True, "source_versions": workspace["source_versions"]})
        assert final["champion_id"] and len(final["standings"]) == size
        assert all(m["assignable"] for m in call("/machine-resources/")["results"])
        runs.append({"size": size, "rounds": rounds, "champion": final["champion_id"]})
    call("/auth/logout/", "POST", {})
    call("/auth/me/", expected=403)
    statuses = [raw("/api/v1/auth/login/", "POST", {}, {"Content-Type": "application/json"}) for _ in range(8)]
    limited = [(json.loads(body), headers) for status, body, headers in statuses if status == 429]
    assert limited and limited[0][0]["error"]["code"] == "login_rate_limited"
    assert limited[0][1]["Retry-After"] == "60"
    print(json.dumps({"result": "PASS", "https": "isolated self-signed CA verified", "requests_including_csrf": count, "session_csrf_proxy_headers_spa_api404_rate_limit": "PASS", "runs": runs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
