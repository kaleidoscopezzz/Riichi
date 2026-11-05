"""Container readiness: serving HTTP, database reachable, migration graph current."""
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
try:
    import django
    django.setup()
    from django.conf import settings
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    headers = {"Host": settings.ALLOWED_HOSTS[0], "X-Forwarded-Proto": "https"}
    with urlopen(Request("http://127.0.0.1:8000/api/v1/health/", headers=headers), timeout=3) as response:
        if response.status != 200:
            raise RuntimeError("HTTP readiness failed")
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        if cursor.fetchone() != (1,):
            raise RuntimeError("Database readiness failed")
    executor = MigrationExecutor(connection)
    if executor.migration_plan(executor.loader.graph.leaf_nodes()):
        raise RuntimeError("Pending migrations; operator must run deploy/migrate.sh")
    connection.close()
except Exception:
    # Never leak connection credentials in Docker health logs.
    print("API not ready: check service logs, database and migration state", file=sys.stderr)
    sys.exit(1)
