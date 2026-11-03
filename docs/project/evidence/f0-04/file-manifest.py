"""List the complete working changes and fingerprint source, without staging."""
import hashlib
from pathlib import Path
import subprocess

root = Path.cwd().resolve()
assert root == Path("D:/Riichi").resolve()
evidence = root / "docs/project/evidence/f0-04"
for name in ["changed-files.txt", "git-status.txt", "source-sha256.txt", "hygiene-final.log", "manifest.log"]:
    (evidence / name).touch(exist_ok=True)
paths = subprocess.check_output(["git", "ls-files", "--modified", "--others", "--exclude-standard", "-z"], cwd=root).decode().split("\0")
paths = sorted(set(path for path in paths if path))
tracked = subprocess.check_output(["git", "diff", "--name-only", "-z"], cwd=root).decode().split("\0")
tracked = [path for path in tracked if path]
counts = f"{len(paths)} files: {len(tracked)} modified tracked, {len(paths) - len(tracked)} untracked"
(evidence / "changed-files.txt").write_text(counts + "\n\n" + "\n".join(paths) + "\n", encoding="utf-8")
status = subprocess.check_output(["git", "status", "--short", "--branch", "--untracked-files=all"], cwd=root).decode()
(evidence / "git-status.txt").write_text(status, encoding="utf-8")
source_paths = [path for path in paths if "/evidence/" not in path]
(evidence / "source-sha256.txt").write_text("\n".join(f"{hashlib.sha256((root / path).read_bytes()).hexdigest()}  {path}" for path in source_paths) + "\n", encoding="utf-8")
print(counts)
