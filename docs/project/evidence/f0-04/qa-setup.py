"""Prepare an isolated SQLite copy; never migrate or seed the development DB.

Run from backend/ with the project virtual environment.
Credentials stay in the ignored .verification directory; never print them.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys

root = Path.cwd().resolve()
assert root == Path("D:/Riichi/backend").resolve()
qa = root / ".verification/f0-04-qa.sqlite3"
assert not qa.exists(), "Do not overwrite existing QA evidence"
source = root / "db.sqlite3"
digest = hashlib.sha256(source.read_bytes()).hexdigest()
with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as original, sqlite3.connect(qa) as target:
    original.backup(target)
    print("Development DB unchanged before QA:", digest)
    for table in ("accounts_user", "players_playerprofile", "machines_mahjongmachine"):
        print(table, original.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.local"
os.environ["DATABASE_URL"] = "sqlite:///.verification/f0-04-qa.sqlite3"
sys.path.insert(0, str(root))
import django
django.setup()
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
assert Path(connection.settings_dict["NAME"]).resolve() == qa
call_command("migrate", interactive=False)
password = secrets.token_urlsafe(24)
os.environ["DJANGO_SUPERUSER_PASSWORD"] = password
call_command("createsuperuser", username="f004_qa_admin", email="", interactive=False)
del os.environ["DJANGO_SUPERUSER_PASSWORD"]
users = get_user_model()
for index in range(1, 25):
    user = users.objects.create_user(username=f"f004_qa_player_{index:02d}", password=password)
    profile = user.player_profile
    profile.nickname = f"验证选手 {index:02d}"
    profile.save()
users.objects.filter(username="f004_qa_player_24").update(is_active=False)
(root / ".verification/f0-04-credentials.json").write_text(json.dumps({"username": "f004_qa_admin", "password": password}), encoding="utf-8")
(root / ".verification/f0-04-development.sha256").write_text(digest, encoding="ascii")
assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
print("PASS: isolated migrated QA DB; official superuser initialization; 24 QA players; development DB unchanged")
