"""Actual file SQLite races, only in the dedicated F0-04 QA database."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
import os
import sys

root = Path.cwd().resolve()
assert root == Path("D:/Riichi/backend").resolve()
sys.path.insert(0, str(root))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.local"
os.environ["DATABASE_URL"] = "sqlite:///.verification/f0-04-qa.sqlite3"
import django
django.setup()
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from tournaments.models import Tournament
from tournaments.services import TournamentConflict, create_tournament, mutate_tournament
assert Path(connection.settings_dict["NAME"]).resolve() == root / ".verification/f0-04-qa.sqlite3"
admin = get_user_model().objects.get(username="f004_qa_admin")
ids = list(get_user_model().objects.filter(username__startswith="f004_qa_player_", is_active=True).order_by("username").values_list("player_profile__id", flat=True)[:8])


def race(functions):
    barrier = Barrier(len(functions))
    def run(fn):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            fn()
            return "ok"
        except TournamentConflict as exc:
            return exc.default_code
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=len(functions)) as pool:
        return list(pool.map(run, functions))


for index in range(6):
    row = create_tournament(admin, {"name": f"并发验证赛事 {index + 1}", "round_count": 3, "participant_ids": ids[:4]})
    operations = [lambda: mutate_tournament(row.pk, start=True)] * 4 if index < 3 else [lambda: mutate_tournament(row.pk, start=True), lambda: mutate_tournament(row.pk, participant_ids=ids[4:]), lambda: mutate_tournament(row.pk, values={"round_count": 6})]
    results = race(operations)
    assert set(results) <= {"ok", "already_started", "tournament_frozen", "tournament_busy"}, results
    row.refresh_from_db()
    if index < 3:
        assert results.count("ok") == 1
    if row.status == "draft":
        mutate_tournament(row.pk, start=True)
        row.refresh_from_db()
    entries = list(row.participants.all())
    assert row.status == "started" and row.started_at
    assert {entry.player_id for entry in entries} in (set(ids[:4]), set(ids[4:]))
    assert all(entry.display_name_snapshot for entry in entries)
    print("race", index + 1, results, "PASS: complete frozen roster", len(entries), "rounds", row.round_count)
print("PASS: six file SQLite races; no HTTP concurrency or PostgreSQL claim")
