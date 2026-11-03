"""Bounded HTTP integration against the local QA server. Never prints credentials.

Run from backend/. Server must explicitly use f0-04-qa.sqlite3.
"""
import hashlib
from http.cookiejar import CookieJar
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

root = Path.cwd().resolve()
assert root == Path("D:/Riichi/backend").resolve()
credential = json.loads((root / ".verification/f0-04-credentials.json").read_text(encoding="utf-8"))
base = "http://127.0.0.1:8000/api/v1"
opener = build_opener(HTTPCookieProcessor(CookieJar()))


def call(path, method="GET", body=None, expected=200, csrf=True):
    headers = {"Accept": "application/json"}
    if method != "GET" and csrf:
        token = call("/auth/csrf/")["data"]["csrf_token"]
        headers["X-CSRFToken"] = token
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
    try:
        response = opener.open(request, timeout=15)
    except HTTPError as error:
        response = error
    payload = json.loads(response.read())
    assert response.code == expected, (method, path, response.code, expected, payload.get("error"))
    if path != "/auth/csrf/":
        print(method, path, response.code)
    return payload


assert call("/health/")["status"] == "ok"
call("/tournaments/", expected=403)
call("/auth/login/", "POST", credential, expected=403, csrf=False)
call("/auth/login/", "POST", credential)
players = call("/players/?eligible=true")["data"]
second = call("/players/?eligible=true&page=2")["data"]
assert players["count"] == 24 and second["results"]
ids = [p["id"] for p in players["results"] + second["results"] if p["username"] != credential["username"]]
row = call("/tournaments/", "POST", {"name": "HTTP 验证草稿", "round_count": 3, "participant_ids": ids[:4]}, expected=201)["data"]
pk = row["id"]
assert row["oka"] == "20" and row["uma"] == ["30", "10", "-10", "-30"]
call(f"/tournaments/{pk}/", "PATCH", {"name": "不应部分保存", "participant_ids": [999999]}, expected=400)
assert call(f"/tournaments/{pk}/")["data"]["name"] == "HTTP 验证草稿"
call(f"/tournaments/{pk}/participants/", "PUT", {"participant_ids": ids[:3]})
call(f"/tournaments/{pk}/start/", "POST", {}, expected=400)
call(f"/tournaments/{pk}/participants/", "PUT", {"participant_ids": [ids[0]] * 4}, expected=400)
for method, path, body in [("POST", "/tournaments/", {"name": "拒绝", "round_count": 1}), ("PATCH", f"/tournaments/{pk}/", {"name": "拒绝"}), ("PUT", f"/tournaments/{pk}/participants/", {"participant_ids": ids[:4]}), ("POST", f"/tournaments/{pk}/start/", {})]:
    call(path, method, body, expected=403, csrf=False)
call(f"/tournaments/{pk}/", "PATCH", {"starting_points": 25001, "uma": ["30.125", "9.875", "-10", "-30"], "participant_ids": ids[:4]})
started = call(f"/tournaments/{pk}/start/", "POST", {})["data"]
assert started["status"] == "started" and started["oka"] == "19.996"
assert all(p["display_name_snapshot"] for p in started["participants"])
call(f"/tournaments/{pk}/", "PATCH", {"name": "拒绝冻结修改"}, expected=409)
call(f"/tournaments/{pk}/participants/", "PUT", {"participant_ids": []}, expected=409)
call(f"/tournaments/{pk}/start/", "POST", {}, expected=409)
for size in (8, 12, 16):
    other = call("/tournaments/", "POST", {"name": f"HTTP {size}人验证", "round_count": 6, "participant_ids": ids[:size]}, expected=201)["data"]
    assert call(f'/tournaments/{other["id"]}/start/', "POST", {})["data"]["expected_table_count"] == size // 4
assert call("/tournaments/?search=HTTP&status=started")["data"]["count"] == 4
call("/auth/logout/", "POST", {})
call("/auth/login/", "POST", {"username": "f004_qa_player_01", "password": credential["password"]})
call("/tournaments/", expected=403)
call("/tournaments/", "POST", {"name": "拒绝", "round_count": 1}, expected=403)
call("/auth/logout/", "POST", {})
assert hashlib.sha256((root / "db.sqlite3").read_bytes()).hexdigest() == (root / ".verification/f0-04-development.sha256").read_text()
print("PASS: actual HTTP lifecycle, precision, atomic rollback, eligibility pagination, four sizes, CSRF and permissions; development DB unchanged")
