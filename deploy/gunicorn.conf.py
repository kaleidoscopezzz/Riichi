"""Environment-tunable sync workers; one DB connection per worker in this app."""
import os

bind = "0.0.0.0:8000"
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
if workers < 1:
    raise ValueError("GUNICORN_WORKERS must be positive")
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30
worker_tmp_dir = "/tmp"
accesslog = "-"
errorlog = "-"
# No query strings, Cookie, token or request body in access logs.
access_log_format = '%(h)s %(m)s %(U)s %(s)s %(L)s'
capture_output = True
# Django owns the proxy trust decision. Do not let Gunicorn independently trust
# arbitrary private peer addresses or X-Forwarded-SSL/X-Forwarded-Protocol.
forwarded_allow_ips = ""
secure_scheme_headers = {}
