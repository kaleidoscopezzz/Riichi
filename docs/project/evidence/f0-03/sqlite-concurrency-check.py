"""Bounded ORM concurrency check, only against the dedicated F0-03 QA database.

Run from backend/ with the project virtual environment. No credentials or HTTP
sessions are read. Does not delete data or modify the development database.
"""
import os
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

sys.path.insert(0, str(Path.cwd()))
os.environ["DATABASE_URL"] = "sqlite:///.verification/f0-03-qa.sqlite3"
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.local"

import django
django.setup()

from django.db import close_old_connections, connection
from machines.models import MahjongMachine
from machines.services import create_machine, change_machine, MachineConflict

database = Path(connection.settings_dict["NAME"]).resolve()
assert database == (Path.cwd() / ".verification/f0-03-qa.sqlite3").resolve()
assert connection.vendor == "sqlite"
assert MahjongMachine.objects.count() == 0, "Dedicated QA DB must start empty"
barrier = Barrier(8)


def worker(number):
    close_old_connections()
    try:
        barrier.wait(timeout=15)
        create_machine({"machine_no": f"{100 + number:03}", "name": f"并发验证设备 {number}", "location": "独立验证环境"})
        return "created"
    except MachineConflict as error:
        return error.default_code
    finally:
        close_old_connections()


with ThreadPoolExecutor(max_workers=8) as pool:
    results = list(pool.map(worker, range(8)))
assert set(results) <= {"created", "machine_capacity_full", "machine_busy"}
count = MahjongMachine.objects.exclude(status="retired").count()
assert 1 <= count <= 4 and count == results.count("created")
print("PASS file SQLite, eight independent connections:", results, "active=", count)

# Explicit sequential preparation for browser capacity checks, not an automatic
# retry of any uncertain HTTP write. All records remain in this ignored QA DB.
for number in range(300, 304):
    if MahjongMachine.objects.exclude(status="retired").count() == 4:
        break
    create_machine({"machine_no": str(number), "name": "容量验证设备", "location": "独立验证环境"})
assert MahjongMachine.objects.exclude(status="retired").count() == 4
try:
    create_machine({"machine_no": "555", "name": "第五台验证设备"})
    raise AssertionError("Unexpected fifth active machine")
except MachineConflict as error:
    assert error.default_code == "machine_capacity_full"
original = MahjongMachine.objects.first()
change_machine(original.pk, {"status": "maintenance"})
change_machine(original.pk, {"status": "disabled"})
assert MahjongMachine.objects.exclude(status="retired").count() == 4
change_machine(original.pk, retire=True)
historical = MahjongMachine.objects.get(pk=original.pk)
assert historical.status == "retired" and historical.capacity_slot is None
assert historical.name == original.name
replacement = create_machine({"machine_no": original.machine_no, "name": "替代物理设备验证"})
assert replacement.pk != original.pk
change_machine(replacement.pk, retire=True)
assert MahjongMachine.objects.exclude(status="retired").count() == 3
print("PASS fifth rejected, maintenance/disabled counted, retirement frees capacity, replacement has new ID; browser QA starts with three active devices.")
print("PostgreSQL concurrency UNVERIFIED. No development data or authentication secrets used.")
