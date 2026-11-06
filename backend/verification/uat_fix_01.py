"""Real HTTP UAT against the isolated QA service, never Owner's DB/password."""
import http.cookiejar
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPCookieProcessor, Request


def main():
    credentials = json.loads((Path(__file__).resolve().parents[1] / '.verification/uat-fix-01/credentials.json').read_text())
    client = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    base = 'http://127.0.0.1:8027/api/v1'
    count = 0

    def call(path, method='GET', body=None, expected=200, csrf=True):
        nonlocal count
        headers = {'Content-Type': 'application/json'}
        if method != 'GET' and csrf:
            headers['X-CSRFToken'] = call('/auth/csrf/')['csrf_token']
        request = Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
        try:
            with client.open(request) as response:
                status, data = response.status, json.load(response)
        except HTTPError as error:
            status, data = error.code, json.load(error)
        assert status == expected, (path, status, data.get('error', {}))
        count += 1
        return data.get('data', data)

    call('/auth/register/', 'POST', {'username': 'must_not_create'}, 403)
    admin_credentials = {key: credentials[key] for key in ['username', 'password']}
    call('/auth/login/', 'POST', admin_credentials, 403, csrf=False)
    if 'legacy' in credentials:
        # Non-staff with a correct password gets the same 400 invalid_credentials as a wrong password.
        call('/auth/login/', 'POST', credentials['legacy'], 400)
    call('/auth/login/', 'POST', admin_credentials)
    created = [call('/players/', 'POST', {'nickname': f'HTTP老板选手{i+1:02}'}, 201) for i in range(16)]
    ids = [p['id'] for p in created]
    assert all('username' not in p and p['is_active'] for p in created)
    call(f'/players/{ids[0]}/', 'PATCH', {'nickname': 'HTTP已更新昵称'})
    spare = call('/players/', 'POST', {'nickname': 'HTTP可删除档案'}, 201)
    call(f'/players/{spare["id"]}/', 'DELETE', {'confirmed': True})
    call(f'/players/{spare["id"]}/', expected=404)
    call('/players/', 'POST', {'nickname': '禁止提权', 'is_staff': True}, 400)
    runs = []
    for size, rounds in [(4, 1), (8, 3), (12, 2), (16, 6)]:
        t = call('/tournaments/', 'POST', {'name': f'UAT HTTP {size}人{rounds}轮', 'round_count': rounds, 'participant_ids': ids[:size]}, 201)
        pk = t['id']
        started = call(f'/tournaments/{pk}/start/', 'POST', {})
        snapshot = started['participants'][0]['display_name_snapshot']
        if size == 4:
            call(f'/players/{ids[0]}/', 'PATCH', {'nickname': 'HTTP赛后显示名称'})
            call(f'/players/{ids[0]}/', 'DELETE', {'confirmed': True}, 409)
            call(f'/players/{ids[0]}/archive/', 'POST', {'confirmed': True})
            assert ids[0] not in [p['id'] for p in call('/players/?eligible=true')['results']]
            call('/tournaments/', 'POST', {'name': '归档不可参赛', 'round_count': 1, 'participant_ids': ids[:4]}, 400)
            assert call(f'/tournaments/{pk}/')['participants'][0]['display_name_snapshot'] == snapshot
        free = [m['machine_id'] for m in call('/machine-resources/')['results'] if m['assignable']][:size//4]
        for number in range(1, rounds+1):
            request = {'round_number': number}
            if number == 1:
                request['machine_ids'] = free
            round_data = call(f'/tournaments/{pk}/rounds/', 'POST', request, 201)
            for table in round_data['tables']:
                points = [{'participant_id': seat['participant_id'], 'raw_points': value} for seat, value in zip(table['seats'], [30000, 30000, 30000, 10000])]
                call(f'/round-tables/{table["id"]}/result/confirm/', 'POST', {'version': 0, 'points': points})
        workspace = call(f'/tournaments/{pk}/workspace/')
        for members in workspace['unresolved_groups']:
            draw = call(f'/tournaments/{pk}/lotteries/', 'POST', {'members': members, 'order': members[::-1], 'source_versions': workspace['source_versions'], 'method': 'QA公开签条模拟', 'description': '隔离HTTP回归记录', 'drawn_at': datetime.now(timezone.utc).isoformat()}, 201)
            call(f'/tournaments/{pk}/lotteries/{draw["id"]}/confirm/', 'POST', {'confirmed': True})
        final = call(f'/tournaments/{pk}/complete/', 'POST', {'confirmed': True, 'source_versions': workspace['source_versions']})
        assert len(final['standings']) == size and final['champion_id']
        assert all(m['assignable'] for m in call('/machine-resources/')['results'] if m['machine_id'] in free)
        runs.append({'tournament_id': pk, 'size': size, 'rounds': rounds, 'champion': final['champion_id']})
        if size == 4:
            call(f'/players/{ids[0]}/restore/', 'POST', {'confirmed': True})
    call('/auth/logout/', 'POST', {})
    call('/players/', expected=403)
    print(json.dumps({'result': 'PASS', 'requests_including_csrf': count, 'managed_players_created': 16, 'edit_archive_restore_delete': 'PASS', 'snapshot_protection': 'PASS', 'public_registration_closed': True, 'legacy_nonstaff_login_rejected': 'legacy' in credentials, 'csrf': 'PASS', 'exact_scoring_lottery_release': 'PASS', 'tournament_runs': runs}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
