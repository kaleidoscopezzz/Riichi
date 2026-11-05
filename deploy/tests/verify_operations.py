"""Destructive-failure simulations ONLY on isolated riichi_qa Compose projects.

Leaves databases, backups and failure logs intact. Runs after qa_runtime.py.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import secrets
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    env_file = Path(args.env_file).resolve()
    values = dict(line.split("=", 1) for line in env_file.read_text().splitlines() if line and not line.startswith("#"))
    assert values["POSTGRES_DB"] == "riichi_qa" and values["COMPOSE_PROJECT_NAME"].startswith("riichi-docker-qa"), "Isolated QA project required"
    work = Path(args.work_dir).resolve()
    assert work.is_relative_to(root / ".verification"), "QA artifacts must stay ignored"
    work.mkdir(parents=True, exist_ok=True)
    logs = work / "operations"
    logs.mkdir(exist_ok=True)
    backups = work / "backups"
    backups.mkdir(exist_ok=True)
    environment = {**os.environ, "RIICHI_ENV_FILE": str(env_file), "RIICHI_BACKUP_DIR": str(backups)}
    compose = ["docker", "compose", "--env-file", str(env_file), "-f", str(root / "deploy/compose.yaml")]
    outcomes = {}

    def invoke(label, command, expected=0, input="", cwd=None, env=None, contains=None):
        result = subprocess.run(command, input=input, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env or environment, cwd=cwd or root, timeout=240)
        (logs / f"{label}.log").write_text(result.stdout + result.stderr)
        assert result.returncode == expected, (label, result.returncode, result.stderr[-500:])
        if contains:
            assert contains in result.stdout + result.stderr, (label, "wrong rejection reason", result.stderr[-500:])
        outcomes[label] = "PASS" if expected == 0 else "EXPECTED_REJECTION"
        return result.stdout

    def script(name):
        return ["bash", str(root / "deploy" / f"{name}.sh")]

    def manifest(label, database=None):
        command = compose + ["run", "--rm", "--no-deps", "-T"]
        if database:
            command += ["-e", "POSTGRES_DB=" + database]
        return json.loads(invoke(label, command + ["api", "python", "-m", "verification.data_manifest"]))

    before = manifest("manifest-before")
    other_cwd = work / "任意 工作目录"
    other_cwd.mkdir(exist_ok=True)
    invoke("status-arbitrary-cwd", script("status"), cwd=other_cwd)
    invoke("migrate-eof", script("migrate"), expected=1, contains="未收到确认")
    invoke("migrate-wrong-confirmation", script("migrate"), expected=1, input="NO\n", contains="确认不匹配")
    invoke("backup-unwritable", script("backup"), expected=1, env={**environment, "RIICHI_BACKUP_DIR": "/dev/null/unwritable"}, contains="FAILED")
    original = set(backups.glob("*.dump"))
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda i: invoke(f"backup-concurrent-{i}", script("backup")), range(2)))
    created = set(backups.glob("*.dump")) - original
    assert len(created) == 2 and all(path.stat().st_size > 0 for path in created)
    archive = sorted(created)[0]
    target = "riichi_qa_restore_" + secrets.token_hex(4)
    base_restore = script("restore") + [str(archive)]
    invoke("restore-live-rejected", base_restore + ["riichi_qa"], expected=1, contains="拒绝目标")
    invoke("restore-unsafe-name", base_restore + ["riichi_qa_restore_bad;DROP"], expected=1, contains="拒绝目标")
    invoke("restore-eof", base_restore + [target], expected=1, contains="未收到确认")
    invoke("restore-wrong-confirmation", base_restore + [target], expected=1, input="NO\n", contains="确认不匹配")
    corrupt = work / "corrupt.dump"
    corrupt.write_text("not a PostgreSQL archive")
    invoke("restore-corrupt", script("restore") + [str(corrupt), target], expected=1, input=f"RESTORE {target}\n", contains="pg_restore")
    invoke("restore-success", base_restore + [target], input=f"RESTORE {target}\n")
    invoke("restore-existing-rejected", base_restore + [target], expected=1, input=f"RESTORE {target}\n", contains="目标库已存在")
    assert manifest("manifest-restored", target) == before
    invoke("restart", compose + ["restart"])
    invoke("wait-after-restart", compose + ["up", "-d", "--wait", "--wait-timeout", "120"])
    assert manifest("manifest-restarted") == before
    invoke("recreate", compose + ["up", "-d", "--force-recreate", "--wait", "--wait-timeout", "120"])
    assert manifest("manifest-recreated") == before
    invoke("db-stop-for-failure", compose + ["stop", "db"])
    invoke("backup-db-unavailable", script("backup"), expected=1, contains="FAILED")
    invoke("db-restart", compose + ["up", "-d", "--wait", "db"])
    assert manifest("manifest-after-failure") == before
    services = {}
    for service in ("api", "nginx", "db"):
        container = invoke(f"id-{service}", compose + ["ps", "-q", service]).strip()
        info = json.loads(subprocess.check_output(["docker", "inspect", container]))[0]
        ports = info["HostConfig"]["PortBindings"] or {}
        networks = list(info["NetworkSettings"]["Networks"])
        if service in ("api", "db"):
            assert not ports, f"{service} must not publish ports"
        else:
            assert set(ports) == {"8080/tcp", "8443/tcp"}
            assert all(binding["HostIp"] == "127.0.0.1" for bindings in ports.values() for binding in bindings)
        if service != "db":
            assert info["Config"]["User"].split(":")[0] not in ("", "0", "root")
            assert info["HostConfig"]["ReadonlyRootfs"]
        services[service] = {"published_ports": sorted(ports), "networks": networks, "user": info["Config"]["User"]}
    for network in ("web", "data"):
        name = values["COMPOSE_PROJECT_NAME"] + "_" + network
        info = json.loads(subprocess.check_output(["docker", "network", "inspect", name]))[0]
        assert info["Internal"]
    assert all(not name.endswith("_data") for name in services["nginx"]["networks"])
    assert all(name.endswith("_data") for name in services["db"]["networks"])
    role = invoke("app-role", compose + ["exec", "-T", "db", "sh", "-c", 'psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=\'riichi\'"'])
    assert role.strip() == "f|f|f"
    print(json.dumps({"result": "PASS", "checks": outcomes, "canonical_counts_hashes_fk_integrity": "equal before/restore/restart/recreate/failure", "concurrent_backups": len(created), "services": services}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
