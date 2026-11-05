"""Real Windows smoke/failure checks against an explicitly marked disposable copy.

Run with the project Python; never point --qa-root at a working checkout.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from uuid import uuid4
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    qa, evidence = args.qa_root.resolve(), args.evidence.resolve()
    source = Path(__file__).resolve().parents[2]
    if os.name != "nt" or qa == source or not (qa / ".launcher-qa").is_file():
        raise SystemExit("Requires Windows and an explicitly marked disposable QA copy.")
    if ".verification" not in qa.parts or not qa.is_relative_to(source):
        raise SystemExit("QA copy must stay under this repository's ignored .verification directory.")
    evidence.mkdir(parents=True, exist_ok=True)
    ps = str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe")
    env = os.environ.copy()
    for key in ["SECRET_KEY", "DATABASE_URL", "DJANGO_SETTINGS_MODULE", "RIICHI_PYTHON", "RIICHI_NODE", "RIICHI_NPM"]:
        env.pop(key.upper(), None)
        env.pop(key, None)
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    results = []

    def run(name, script="start.ps1", extra=(), variables=None, answer=None, expected=0, root=qa):
        local = env | (variables or {})
        command = [ps, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(root / "scripts" / script)]
        if script == "start.ps1":
            command += ["-NoBrowser"]
            if answer is None:
                command += ["-NonInteractive"]
        command += list(extra)
        start = time.monotonic()
        completed = subprocess.run(command, cwd=root, env=local, input=answer or "", capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=150)
        output = completed.stdout + completed.stderr
        (evidence / f"{name}.txt").write_text(output, encoding="utf-8")
        assert completed.returncode == expected, (name, completed.returncode, output[-1200:])
        results.append({"case": name, "exit": completed.returncode, "seconds": round(time.monotonic()-start, 2), "result": "PASS"})
        return output

    def state():
        return json.loads((qa / ".runtime/launcher/state.json").read_text(encoding="utf-8-sig"))

    def free_ports():
        # Never stop the occupant. Check that the launcher's rollback released its own sockets.
        for port in [8000, 5173]:
            with socket.socket() as test:
                test.bind(("127.0.0.1", port))

    def assert_failure_cleanup():
        assert not (qa / ".runtime/launcher/state.json").exists()
        free_ports()

    free_ports()
    output = run("daily-start", variables={"VITE_API_BASE_URL": "https://example.invalid"})
    assert "跳过安装" in output and "尚无有效管理员" in output
    initial = state()
    with urlopen("http://127.0.0.1:8000/api/v1/health/") as response:
        assert json.load(response)["service"] == "riichi-api"
    with urlopen("http://127.0.0.1:5173/api/v1/health/") as response:
        assert json.load(response)["status"] == "ok"
    with urlopen("http://127.0.0.1:5173/src/services/api.ts") as response:
        transformed = response.read().decode()
        assert '"VITE_API_BASE_URL": "http://127.0.0.1:5173"' in transformed
    run("repeat-start")
    assert state()["owner"] == initial["owner"]
    run("normal-stop", "stop.ps1")
    assert_failure_cleanup()
    identities = [initial[key] for key in ["owner", "backend", "frontend"]]
    checks = []
    for identity in identities:
        checks.append(f"$entry=[RiichiLauncher.ProcessJob]::Snapshot({identity['ProcessId']}); if ($null -ne $entry -and $entry.CreationTime -eq '{identity['CreationTime']}') {{ throw 'Owned process survived job closure' }}")
    command = f". '{(qa / 'scripts/common.ps1').as_posix()}'; " + "; ".join(checks)
    subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command], env=env, check=True, capture_output=True)
    run("no-running-services", "stop.ps1")
    stale = qa / ".runtime/launcher/state.json"
    stale.write_text(json.dumps(initial), encoding="utf-8")
    run("exited-process", "stop.ps1")
    assert not stale.exists()

    for port in [8000, 5173]:
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", port))
            occupied.listen()
            output = run(f"port-{port}-occupied", expected=1)
            assert f"端口 {port}" in output and occupied.fileno() != -1
            assert not stale.exists()

    for key, label in [("RIICHI_NODE", "node"), ("RIICHI_NPM", "npm")]:
        output = run(f"missing-{label}", variables={key: str(qa / f"missing-{label}.exe")}, expected=1)
        assert "不存在" in output

    # No virtual environment/runtime in this second tiny copy: test an actually
    # unavailable Python path without renaming or uninstalling anybody's Python.
    probe = qa.parent / "missing-python-copy"
    import shutil
    (probe / "backend").mkdir(parents=True, exist_ok=True)
    (probe / "scripts").mkdir(exist_ok=True)
    for file in (qa / "scripts").iterdir():
        if file.is_file():
            shutil.copyfile(file, probe / "scripts" / file.name)
    shutil.copyfile(qa / "backend/.python-version", probe / "backend/.python-version")
    output = run("missing-python", variables={"RIICHI_PYTHON": str(probe / "absent.exe")}, root=probe, expected=1)
    assert "不存在" in output

    # Cancellation and connection failure never initialize a database silently.
    new_database = qa / f"backend/launcher-unmigrated-{uuid4().hex}.sqlite3"
    assert not new_database.exists(), "Use a fresh QA copy for the migration case."
    variables = {"DATABASE_URL": "sqlite:///" + new_database.as_posix()}
    run("pending-migrations-no-consent", variables=variables, expected=1)
    assert not new_database.exists()
    run("pending-migrations-cancel", variables=variables, answer="CANCEL\n", expected=1)
    assert not new_database.exists()
    run("pending-migrations-confirm", variables=variables, answer="MIGRATE\n")
    assert new_database.exists()
    run("migration-case-stop", "stop.ps1")
    # Closed local PostgreSQL port, no credentials or external server probing.
    run("database-unavailable", variables={"DATABASE_URL": "postgresql://127.0.0.1:1/launcher_qa"}, expected=1)
    assert_failure_cleanup()

    manage = qa / "backend/manage.py"
    original = manage.read_bytes()
    try:
        manage.write_bytes(b"raise SystemExit(53)\n" + original)
        run("backend-exits", expected=1)
        assert_failure_cleanup()
    finally:
        manage.write_bytes(original)
    config = qa / "frontend/vite.config.ts"
    original = config.read_bytes()
    try:
        config.write_bytes(b"throw new Error('Isolated QA frontend startup failure')\n" + original)
        run("frontend-exits", expected=1)
        assert_failure_cleanup()
    finally:
        config.write_bytes(original)

    # Reuse simulation: a real unrelated test process, a stale creation time,
    # then a correct PID/time with an unrelated command line. Both must survive.
    child = subprocess.Popen([env.get("COMSPEC", str(Path(os.environ["SystemRoot"]) / "System32/cmd.exe")), "/d", "/c", "pause"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
    try:
        code = f". '{(qa / 'scripts/common.ps1').as_posix()}'; [RiichiLauncher.ProcessJob]::Snapshot({child.pid}) | ConvertTo-Json -Compress"
        snapshot = subprocess.check_output([ps,"-NoProfile","-ExecutionPolicy","Bypass","-Command",code], env=env).decode("utf-8-sig").strip()
        identity = json.loads(snapshot)
        fake = initial | {"owner": identity}
        fake["owner"] = identity | {"CreationTime": str(int(identity["CreationTime"])-1)}
        stale.write_text(json.dumps(fake), encoding="utf-8")
        run("pid-reuse-refused", "stop.ps1", expected=1)
        assert child.poll() is None
        fake["owner"] = identity
        stale.write_text(json.dumps(fake), encoding="utf-8")
        run("unrelated-command-refused", "stop.ps1", expected=1)
        assert child.poll() is None
    finally:
        # Only this test's child, whose subprocess handle is retained.
        child.terminate()
        child.wait(timeout=10)
        stale.unlink(missing_ok=True)
    free_ports()
    (evidence / "smoke-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"result": "PASS", "cases": len(results), "shell": "Windows PowerShell 5.1", "qa_path_contains_chinese_and_spaces": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
