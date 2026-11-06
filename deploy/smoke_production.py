"""Read-only public HTTPS smoke. Never seeds data or accepts an insecure TLS mode."""
import argparse
import json
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check(url, wait_tls=0):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('Supply a single HTTPS origin, without credentials/path/query.')
    origin = url.rstrip('/')
    client = build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))

    def get(path, headers=None):
        request = Request(origin + path, headers=headers or {})
        try:
            response = client.open(request, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.read(), response.headers

    # On first install ACME acquisition is asynchronous. Retry only transport
    # failures during startup. An HTTP response is evaluated exactly once.
    deadline = time.monotonic() + wait_tls
    while True:
        try:
            login = get('/login')
            break
        except URLError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(3)
    for status, body, headers in (login, get('/tournaments')):
        assert status == 200 and b'<div id="root">' in body, 'SPA routing failed'
        assert headers.get('X-Content-Type-Options') == 'nosniff', 'Missing security header'
    status, body, _ = get('/api/v1/health/')
    payload = json.loads(body)
    assert status == 200 and payload.get('data', payload)['status'] == 'ok', 'API liveness failed'
    for forged in (
        {'X-Forwarded-Proto': 'http', 'X-Forwarded-Host': 'evil.invalid'},
        {'X-Forwarded-Proto': 'https,http', 'X-Forwarded-For': '192.0.2.99', 'X-Real-IP': '192.0.2.88', 'Forwarded': 'proto=http;host=evil.invalid'},
    ):
        assert get('/api/v1/health/', forged)[0] == 200, 'Proxy-header handling/redirect failed'
    assert get('/api/v1/not-a-real-endpoint/')[0] == 404, 'API fallback failed'
    assert get('/assets/not-a-real-file.js')[0] == 404, 'Asset fallback failed'
    assert get('/.env')[0] == 404, 'Hidden-file protection failed'
    http_origin = 'http://' + parsed.hostname
    try:
        response = client.open(Request(http_origin + '/login'), timeout=20)
    except HTTPError as error:
        response = error
    with response:
        assert response.status in (301, 308) and response.headers.get('Location') == origin + '/login', 'Canonical HTTPS redirect failed'
    return {'result': 'PASS', 'tls': 'system trust required', 'checks': ['SPA', 'liveness', 'proxy headers', '404', 'security header', 'HTTP redirect'], 'business_writes': 0, 'admin_browser_login': 'separate Owner verification required'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--wait-tls', type=int, choices=range(181), default=0, metavar='SECONDS')
    arguments = parser.parse_args()
    print(json.dumps(check(arguments.url, arguments.wait_tls), ensure_ascii=False, indent=2))
