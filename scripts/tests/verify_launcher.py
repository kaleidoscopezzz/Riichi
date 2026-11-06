"""Real Windows smoke/failure checks against an explicitly marked disposable copy.

Run with the project Python; never point --qa-root at a working checkout.
--self-test runs only the installation-free sub-tests (Python discovery
fallback, PID-reuse self-healing) in a fresh sandbox under --evidence.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from uuid import uuid4
from urllib.request import urlopen

# Stand-in python.exe / py.exe for discovery checks; no real runtime involved.
FAKE_PYTHON = r'''
using System;
using System.IO;
public static class FakePython {
    // version.txt beside the copy: "missing" acts like a Python Launcher
    // without 3.13 (stderr + exit 103); otherwise report that version.
    public static int Main(string[] args) {
        string self = System.Reflection.Assembly.GetEntryAssembly().Location;
        string version = File.ReadAllText(Path.Combine(Path.GetDirectoryName(self), "version.txt")).Trim();
        string joined = String.Join(" ", args);
        if (version == "missing") { Console.Error.WriteLine("Python 3.13 not found!"); return 103; }
        if (joined.Contains("sys.executable")) { Console.WriteLine(self); return 0; }
        if (joined.Contains("version_info")) { Console.WriteLine(version); return 0; }
        return 2;
    }
}
'''


def has_cjk_and_space(path):
    text = str(path)
    # CJK Unified Ideographs (+Ext A), Compatibility Ideographs, Ext B and later.
    cjk = any("\u3400" <= ch <= "\u9fff" or "\uf900" <= ch <= "\ufaff" or "\U00020000" <= ch <= "\U0002ffff" for ch in text)
    return cjk and " " in text


def fake_python(ps, env, folder, name, version):
    """Copy the compiled stand-in to folder/name with its version.txt."""
    exe = folder.parent / "fake-python.exe"
    if not exe.exists():
        exe.parent.mkdir(parents=True, exist_ok=True)
        (exe.parent / "FakePython.cs").write_text(FAKE_PYTHON, encoding="utf-8")
        subprocess.run([ps, "-NoProfile", "-Command", "Add-Type -Path $env:FAKE_SOURCE -OutputAssembly $env:FAKE_EXE -OutputType ConsoleApplication"],
                       env=env | {"FAKE_SOURCE": str(exe.parent / "FakePython.cs"), "FAKE_EXE": str(exe)}, check=True, capture_output=True)
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(exe, folder / name)
    (folder / "version.txt").write_text(version, encoding="ascii")
    return folder / name


def self_test(ps, env, source, work):
    """Installation-free checks in a new CJK+space sandbox; only test-owned processes."""
    sandbox = work / f"Riichi 自测 {uuid4().hex[:8]}"
    assert has_cjk_and_space(sandbox)
    (sandbox / "scripts").mkdir(parents=True)
    (sandbox / "backend").mkdir()
    for name in ["common.ps1", "start.ps1", "stop.ps1", "run.ps1", "LauncherProcess.cs"]:
        shutil.copyfile(source / "scripts" / name, sandbox / "scripts" / name)
    shutil.copyfile(source / "backend/.python-version", sandbox / "backend/.python-version")
    minimum = (sandbox / "backend/.python-version").read_text(encoding="utf-8").strip()
    system = [str(Path(os.environ["SystemRoot"]) / part) for part in ["System32", "", "System32/Wbem", "System32/WindowsPowerShell/v1.0"]]
    results = []

    def powershell(name, command, variables=None, expected=0, script=None, args=()):
        target = ["-File", str(sandbox / "scripts" / script), *args] if script else ["-Command", ". (Join-Path $env:RIICHI_SANDBOX 'scripts\\common.ps1'); " + command]
        start = time.monotonic()
        completed = subprocess.run([ps, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", *target], cwd=sandbox,
                                   env=env | {"RIICHI_SANDBOX": str(sandbox)} | (variables or {}), capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=150)
        output = completed.stdout + completed.stderr
        (work / f"self-{name}.txt").write_text(output, encoding="utf-8")
        assert completed.returncode == expected, (name, completed.returncode, output[-1200:])
        results.append({"case": f"self-{name}", "exit": completed.returncode, "seconds": round(time.monotonic()-start, 2), "result": "PASS"})
        return output

    # L2: a Python Launcher without 3.13 writes stderr and exits non-zero; the
    # search must go on to .tools\python and PATH instead of aborting.
    py_missing = fake_python(ps, env, work / "tools/py-missing", "py.exe", "missing")
    path_310 = fake_python(ps, env, work / "tools/path-python-310", "python.exe", "3.10.11")
    local = fake_python(ps, env, sandbox / ".tools/python/3.13", "python.exe", minimum)
    search = {"PATH": ";".join([str(py_missing.parent), str(path_310.parent), *system]), "RIICHI_MINIMUM": minimum}
    find = "$found = Find-Python ([version]$env:RIICHI_MINIMUM); 'FOUND=' + $found"
    output = powershell("discovery-py-without-3.13", find, search)
    assert f"FOUND={local}".lower() in output.lower() and "NativeCommandError" not in output, output
    shutil.rmtree(sandbox / ".tools")
    output = powershell("discovery-all-candidates-fail", find, search)
    assert output.strip().splitlines()[-1] == "FOUND=", output

    # L1: owner PID now held by an unrelated live process created at another
    # time. start/stop must clear the stale state; the process must survive.
    stale = sandbox / ".runtime/launcher/state.json"
    child = subprocess.Popen([env.get("COMSPEC", str(Path(os.environ["SystemRoot"]) / "System32/cmd.exe")), "/d", "/c", "pause"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
    try:
        identity = json.loads(powershell("child-identity", f"[RiichiLauncher.ProcessJob]::Snapshot({child.pid}) | ConvertTo-Json -Compress").strip().splitlines()[-1])
        reused = identity | {"CreationTime": str(int(identity["CreationTime"]) - 1)}

        def write(owner, backend=None):
            stale.parent.mkdir(parents=True, exist_ok=True)
            stale.write_text(json.dumps({"root": str(sandbox), "runId": uuid4().hex, "owner": owner, "status": "ready", "backend": backend, "frontend": None, "error": None}), encoding="utf-8")

        write(reused)
        # Stops before any installation: RIICHI_PYTHON points to a missing file.
        output = powershell("start-pid-reuse-self-heals", "", {"RIICHI_PYTHON": str(sandbox / "absent-python.exe")}, 1, "start.ps1", ["-NoBrowser", "-NonInteractive"])
        assert "旧进程已退出，已清理本项目过期状态" in output and ("不存在" in output or "端口" in output), output
        assert not stale.exists() and child.poll() is None
        write(reused)
        output = powershell("stop-pid-reuse-cleans", "", script="stop.ps1")
        assert "已不存在" in output and not stale.exists() and child.poll() is None, output
        write(identity)
        output = powershell("stop-same-creation-foreign-command-refused", "", expected=1, script="stop.ps1")
        assert "命令行不属于本次 Riichi 启动" in output and stale.exists() and child.poll() is None, output
        write(reused, backend=identity)
        output = powershell("stop-surviving-child-refused", "", expected=1, script="stop.ps1")
        assert "仍以原身份运行" in output and stale.exists() and child.poll() is None, output
    finally:
        # Only this test's child, whose subprocess handle is retained.
        child.terminate()
        child.wait(timeout=10)
        stale.unlink(missing_ok=True)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--self-test", action="store_true", help="only the installation-free sub-tests; no QA copy needed")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[2]
    evidence = args.evidence.resolve()
    if os.name != "nt":
        raise SystemExit("Requires Windows.")
    if not args.self_test:
        if args.qa_root is None:
            parser.error("--qa-root is required unless --self-test is given")
        qa = args.qa_root.resolve()
        if qa == source or not (qa / ".launcher-qa").is_file():
            raise SystemExit("Requires an explicitly marked disposable QA copy.")
        if ".verification" not in qa.parts or not qa.is_relative_to(source):
            raise SystemExit("QA copy must stay under this repository's ignored .verification directory.")
        if not has_cjk_and_space(qa):
            raise SystemExit("QA copy path must contain Chinese (CJK) characters and a space.")
    evidence.mkdir(parents=True, exist_ok=True)
    ps = str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe")
    env = os.environ.copy()
    for key in ["SECRET_KEY", "DATABASE_URL", "DJANGO_SETTINGS_MODULE", "RIICHI_PYTHON", "RIICHI_NODE", "RIICHI_NPM"]:
        env.pop(key.upper(), None)
        env.pop(key, None)
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    results = self_test(ps, env, source, evidence / f"self-test-{uuid4().hex[:8]}")
    if args.self_test:
        (evidence / "self-test-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"result": "PASS", "cases": len(results), "shell": "Windows PowerShell 5.1", "mode": "self-test"}, ensure_ascii=False))
        return

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

    # Reuse simulation: a real unrelated test process. A different creation
    # time proves the owner exited: stop clears the state, never touching the
    # process. Same PID/time with an unrelated command line stays refused.
    child = subprocess.Popen([env.get("COMSPEC", str(Path(os.environ["SystemRoot"]) / "System32/cmd.exe")), "/d", "/c", "pause"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
    try:
        code = f". '{(qa / 'scripts/common.ps1').as_posix()}'; [RiichiLauncher.ProcessJob]::Snapshot({child.pid}) | ConvertTo-Json -Compress"
        snapshot = subprocess.check_output([ps,"-NoProfile","-ExecutionPolicy","Bypass","-Command",code], env=env).decode("utf-8-sig").strip()
        identity = json.loads(snapshot)
        fake = initial | {"owner": identity}
        fake["owner"] = identity | {"CreationTime": str(int(identity["CreationTime"])-1)}
        stale.write_text(json.dumps(fake), encoding="utf-8")
        output = run("pid-reuse-stale-cleared", "stop.ps1")
        assert "已不存在" in output and not stale.exists() and child.poll() is None
        fake["owner"] = identity
        stale.write_text(json.dumps(fake), encoding="utf-8")
        run("unrelated-command-refused", "stop.ps1", expected=1)
        assert stale.exists() and child.poll() is None
    finally:
        # Only this test's child, whose subprocess handle is retained.
        child.terminate()
        child.wait(timeout=10)
        stale.unlink(missing_ok=True)
    free_ports()
    (evidence / "smoke-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"result": "PASS", "cases": len(results), "shell": "Windows PowerShell 5.1", "qa_path_contains_chinese_and_spaces": has_cjk_and_space(qa)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
