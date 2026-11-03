"""Run the real concurrent service tests on an isolated FILE SQLite database.

Run from backend/. No credentials, HTTP sessions, or development data are used.
The runner-created file is retained as ignored evidence, never overwritten.
"""
import os
from pathlib import Path
import sys

root = Path.cwd().resolve()
assert root == Path("D:/Riichi/backend").resolve()
suffix = "-final" if "--final" in sys.argv else ""
target = root / f".verification/f0-05-concurrency{suffix}.sqlite3"
assert not target.exists(), "Do not overwrite an earlier concurrency run"
os.environ["DATABASE_URL"] = "sqlite:///.verification/f0-05-qa.sqlite3"
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.local"
sys.path.insert(0, str(root))
import django
django.setup()
from django.conf import settings
from django.test.runner import DiscoverRunner
from django.db import connections
connections["default"].settings_dict["TEST"]["NAME"] = str(target)
print("File SQLite concurrency database:", target)
result = DiscoverRunner(verbosity=2, interactive=False, keepdb=True).run_tests(["tournaments.tests_rounds.ConcurrentRoundTests"])
assert result == 0
print("PASS actual file SQLite: same event, cross-event allocation, machine state/retirement, reassignment/release competitions")
