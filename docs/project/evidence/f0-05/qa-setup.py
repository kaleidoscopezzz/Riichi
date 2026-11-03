"""Run from backend/. Migrate a new QA copy, never the development database."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys

root = Path.cwd().resolve()
assert root == Path("D:/Riichi/backend").resolve()
qa = root / ".verification/f0-05-qa.sqlite3"
assert not qa.exists(), "Never overwrite earlier QA data"
source = root / "db.sqlite3"
digest = hashlib.sha256(source.read_bytes()).hexdigest()
with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as original, sqlite3.connect(qa) as target:
    original.backup(target)
    print("Development SHA256", digest)
    for table in ["accounts_user", "players_playerprofile", "machines_mahjongmachine"]:
        print(table, original.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
os.environ["DATABASE_URL"] = "sqlite:///.verification/f0-05-qa.sqlite3"
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.local"
sys.path.insert(0, str(root))
import django
django.setup()
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.db import connection
from machines.services import create_machine
from tournaments.services import create_tournament, mutate_tournament
assert Path(connection.settings_dict["NAME"]).resolve() == qa
call_command("migrate", interactive=False)
password = secrets.token_urlsafe(24)
os.environ["DJANGO_SUPERUSER_PASSWORD"] = password
call_command("createsuperuser", username="f005_qa_admin", email="", interactive=False)
del os.environ["DJANGO_SUPERUSER_PASSWORD"]
User = get_user_model()
admin = User.objects.get(username="f005_qa_admin")
ids = []
for index in range(1, 17):
    user = User.objects.create_user(username=f"f005_qa_player_{index:02d}", password=password)
    profile = user.player_profile
    profile.nickname = f"验证选手 {index:02d}"
    profile.save()
    ids.append(profile.pk)
for number in ["007", "107", "207", "307"]:
    create_machine({"name": f"验证麻将机 {number}", "machine_no": number, "location": "独立QA环境"})
for size in [4, 8, 12, 16]:
    row = create_tournament(admin, {"name": f"QA {size}人首轮联调", "description": "独立验证环境，不是正式或演示赛事", "round_count": 3, "participant_ids": ids[:size]})
    mutate_tournament(row.pk, start=True)
create_tournament(admin, {"name": "QA 草稿边界", "round_count": 1, "participant_ids": ids[:4]})
(root / ".verification/f0-05-credentials.json").write_text(json.dumps({"username": "f005_qa_admin", "password": password}), encoding="utf-8")
(root / ".verification/f0-05-development.sha256").write_text(digest)
assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
print("PASS isolated QA migrated and seeded; development DB unchanged; no credentials printed")
