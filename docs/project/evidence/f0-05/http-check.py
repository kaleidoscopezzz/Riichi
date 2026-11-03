"""Bounded actual HTTP requests against the dedicated localhost QA database.

Run from backend/. Prints statuses, never credentials/Cookie/CSRF values.
"""
from http.cookiejar import CookieJar
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

root = Path.cwd().resolve()
assert root == Path("D:/Riichi/backend").resolve()
credential = json.loads((root / ".verification/f0-05-credentials.json").read_text())
opener = build_opener(HTTPCookieProcessor(CookieJar()))
base = "http://127.0.0.1:8000/api/v1"


def call(path, method="GET", body=None, expected=200, csrf=True):
    headers = {"Accept": "application/json"}
    if method != "GET" and csrf:
        headers["X-CSRFToken"] = call("/auth/csrf/")["data"]["csrf_token"]
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(base + path, method=method, headers=headers, data=json.dumps(body).encode() if body is not None else None)
    try:
        response = opener.open(request, timeout=15)
    except HTTPError as error:
        response = error
    data = json.loads(response.read())
    assert response.code == expected, (method, path, response.code, expected, data.get("error"))
    if path != "/auth/csrf/":
        print(method, path, response.code)
    return data


assert call("/health/")["status"] == "ok"
call("/machine-resources/", expected=403)
call("/auth/login/", "POST", credential)
players = call("/players/?eligible=true")["data"]["results"]
ids = [p["id"] for p in players if p["username"] != credential["username"]]
pool = call("/machine-resources/")["data"]["results"]
assert len(pool) == 4 and all(m["assignable"] for m in pool)
draft = call("/tournaments/", "POST", {"name": "HTTP 首轮事务验证", "round_count": 3, "participant_ids": ids[:8]}, 201)["data"]
pk = draft["id"]
call(f"/tournaments/{pk}/rounds/", "POST", {"round_number": 1}, 409)
call(f"/tournaments/{pk}/start/", "POST", {})
round = call(f"/tournaments/{pk}/rounds/", "POST", {"round_number": 1}, 201)["data"]
assert len(round["tables"]) == 2
assert [t["active_allocation"]["machine_no"] for t in round["tables"]] == ["007", "107"]
assert len({s["participant_id"] for t in round["tables"] for s in t["seats"]}) == 8
for table in round["tables"]:
    assert [s["seat_wind"] for s in table["seats"]] == ["east", "south", "west", "north"]
call(f"/tournaments/{pk}/rounds/", "POST", {"round_number": 1}, 409)
assert call(f"/tournaments/{pk}/rounds/1/")["data"] == round
call(f"/tournaments/{pk}/rounds/", "POST", {"round_number": 2}, 409)
table = round["tables"][0]
tid = table["id"]
machine_id = table["active_allocation"]["machine_id"]
for method, path, body in [("POST", f"/tournaments/{pk}/rounds/", {"round_number": 1}), ("POST", f"/round-tables/{tid}/machine/reassign/", {"machine_id": pool[2]["machine_id"]}), ("POST", f"/round-tables/{tid}/machine/release/", {})]:
    call(path, method, body, 403, csrf=False)
call(f"/machines/{machine_id}/", "PATCH", {"status": "disabled"}, 409)
call(f"/machines/{machine_id}/retire/", "POST", {}, 409)
changed = call(f"/round-tables/{tid}/machine/reassign/", "POST", {"machine_id": pool[2]["machine_id"]})["data"]
assert len(changed["allocation_history"]) == 2 and changed["allocation_history"][0]["status"] == "released"
released = call(f"/round-tables/{tid}/machine/release/", "POST", {"reason": "HTTP验证结束，非成绩确认"})["data"]
assert released["active_allocation"] is None and released["seats"] == table["seats"]
call(f"/round-tables/{tid}/machine/release/", "POST", {}, 409)
call(f"/round-tables/{tid}/machine/reassign/", "POST", {"machine_id": machine_id}, 409)
assert len(call(f"/round-tables/{tid}/machine/history/")["data"]["results"]) == 2
for other in round["tables"][1:]:
    call(f'/round-tables/{other["id"]}/machine/release/', "POST", {"reason": "HTTP验证资源归还"})
assert all(m["assignable"] for m in call("/machine-resources/")["data"]["results"])
call("/auth/logout/", "POST", {})
call("/auth/login/", "POST", {"username": "f005_qa_player_01", "password": credential["password"]})
for path in [f"/tournaments/{pk}/rounds/", f"/tournaments/{pk}/rounds/1/", f"/round-tables/{tid}/", f"/round-tables/{tid}/machine/history/", "/machine-resources/"]:
    call(path, expected=403)
call(f"/round-tables/{tid}/machine/release/", "POST", {}, 403)
call("/auth/logout/", "POST", {})
print("PASS actual HTTP: persisted seating, machine order, CSRF, permissions, state protection, reassignment/release/history and unsupported rounds")
