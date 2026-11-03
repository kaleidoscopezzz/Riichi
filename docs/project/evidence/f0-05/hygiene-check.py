"""Read-only Git, secret/ignore and development DB checks; run from repo root."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

root = Path.cwd().resolve()
assert root == Path("D:/Riichi").resolve()
def git(*args):
    return subprocess.check_output(["git", *args], cwd=root).decode("utf-8").strip()
assert git("branch", "--show-current") == "main"
head = "434a8aa9ae5bd075705322e0556688b7424db16a"
assert git("rev-parse", "HEAD") == head
for stage, sha in [("01", "94a1fec747806682602dd24f7edbbcc4e27d07f0"), ("02", "59be947ca133dbe18a63dcdc99e55a3243daed51"), ("03", "0d7e96b0b920e490abbf7acd1d4aba38493025f9"), ("04", head)]:
    assert git("rev-parse", f"baseline/F0-{stage}^{{commit}}") == sha
    print(f"PASS baseline/F0-{stage}", sha)
paths = [p for p in git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0") if p]
values = [json.loads((root / "backend/.verification/f0-05-credentials.json").read_text())["password"].encode()]
for line in (root / "backend/.env").read_text().splitlines():
    if line.startswith("SECRET_KEY="):
        values.append(line.split("=", 1)[1].strip().strip("\"'").encode())
patterns = [rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", rb"gh[pousr]_[A-Za-z0-9]{30,}", rb"github_pat_[A-Za-z0-9_]{30,}"]
for name in paths:
    path = root / name
    assert not any(part in {"node_modules", ".venv", ".verification", "dist", "__pycache__", ".tools"} for part in Path(name).parts), name
    assert path.name != ".env" and path.suffix not in {".sqlite3", ".sqlite", ".pem", ".key"}, name
    data = path.read_bytes()
    assert not any(value and value in data for value in values), f"Sensitive value found in {name}"
    assert not any(re.search(pattern, data) for pattern in patterns), f"Token/private key pattern found in {name}"
for name in ["backend/.env", "backend/.venv/", "backend/db.sqlite3", "backend/.verification/f0-05-qa.sqlite3", "backend/.verification/f0-05-concurrency.sqlite3", "backend/.verification/f0-05-concurrency-final.sqlite3", "backend/.verification/f0-05-credentials.json", "frontend/node_modules/", "frontend/dist/", ".tools/", "frontend/.cache/"]:
    assert git("check-ignore", name), name
    print("PASS ignored", name)
historical = ["backend/accounts", "backend/players", "backend/common", "backend/tournaments/tests.py", "backend/tournaments/services.py", "backend/tournaments/migrations/0001_initial.py", "backend/machines/models.py", "backend/machines/tests.py", "backend/machines/serializers.py", "backend/machines/views.py", "backend/machines/migrations", "frontend/src/services/api.ts", "frontend/package.json", "frontend/package-lock.json", "backend/requirements.txt"]
historical += [f"docs/project/evidence/f0-{stage:02}" for stage in range(1, 5)] + ["docs/project/evidence/f0-01-candidate"]
assert not git("diff", "--name-only", "baseline/F0-04", "--", *historical)
assert not git("diff", "--cached", "--name-only")
assert not git("diff", "--check")
assert hashlib.sha256((root / "backend/db.sqlite3").read_bytes()).hexdigest() == (root / "backend/.verification/f0-05-development.sha256").read_text()
print("PASS development database SHA256 unchanged; no migration/QA data written there")
print("PASS targeted secret scan, artifacts, original tests/migrations/evidence and dependency locks unchanged")
print(git("status", "--short", "--branch"))
