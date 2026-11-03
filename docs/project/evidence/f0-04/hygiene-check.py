"""Read-only Git, secret, ignored-artifact and development database checks."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

root = Path.cwd().resolve()
assert root == Path("D:/Riichi").resolve()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=root).decode("utf-8").strip()


head = git("rev-parse", "HEAD")
assert head == "0d7e96b0b920e490abbf7acd1d4aba38493025f9"
assert git("branch", "--show-current") == "main"
for stage, sha in [("01", "94a1fec747806682602dd24f7edbbcc4e27d07f0"), ("02", "59be947ca133dbe18a63dcdc99e55a3243daed51"), ("03", head)]:
    assert git("rev-parse", f"baseline/F0-{stage}^{{commit}}") == sha
    print(f"PASS baseline/F0-{stage}", sha)
paths = [p for p in git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0") if p]
secrets = [json.loads((root / "backend/.verification/f0-04-credentials.json").read_text())["password"].encode()]
for line in (root / "backend/.env").read_text().splitlines():
    if line.startswith("SECRET_KEY="):
        secrets.append(line.split("=", 1)[1].strip().strip("\"'").encode())
patterns = [rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", rb"gh[pousr]_[A-Za-z0-9]{30,}", rb"github_pat_[A-Za-z0-9_]{30,}"]
for name in paths:
    path = root / name
    assert not any(part in {"node_modules", ".venv", ".verification", "dist", "__pycache__", ".tools"} for part in Path(name).parts), name
    assert path.name != ".env" and path.suffix not in {".sqlite3", ".sqlite", ".pem", ".key"}, name
    data = path.read_bytes()
    assert not any(secret and secret in data for secret in secrets), f"Sensitive value found in {name}"
    assert not any(re.search(pattern, data) for pattern in patterns), f"Token/private key pattern found in {name}"
for name in ["backend/.env", "backend/.venv/", "backend/db.sqlite3", "backend/.verification/f0-04-qa.sqlite3", "backend/.verification/f0-04-credentials.json", "frontend/node_modules/", "frontend/dist/", ".tools/", "frontend/.cache/"]:
    assert git("check-ignore", name), name
    print("PASS ignored", name)
assert not git("diff", "--name-only", "baseline/F0-03", "--", "backend/accounts", "backend/machines", "backend/common", "backend/players/serializers.py", "frontend/src/services/api.ts", "frontend/package.json", "frontend/package-lock.json", "backend/requirements.txt", "docs/project/evidence/f0-01", "docs/project/evidence/f0-01-candidate", "docs/project/evidence/f0-02", "docs/project/evidence/f0-03")
assert not git("diff", "--check")
db = root / "backend/db.sqlite3"
assert hashlib.sha256(db.read_bytes()).hexdigest() == (root / "backend/.verification/f0-04-development.sha256").read_text()
print("PASS development database SHA256 unchanged; no F0-04 migration or QA seed written there")
print("PASS targeted secret scan, artifacts, historical source/evidence and dependency locks unchanged")
print("Git status:")
print(git("status", "--short", "--branch"))
