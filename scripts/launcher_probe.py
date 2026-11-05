"""Local launcher checks. Never emit secrets or write a database while probing."""
import contextlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def main():
    mode = sys.argv[1]
    if mode == "dependencies":
        for line in (BACKEND / "requirements.txt").read_text().splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            name, version = line.strip().split("==")
            if importlib.metadata.version(name) != version:
                raise RuntimeError("Python 依赖版本不匹配")
        return {"ok": True}
    if mode == "configure":
        template = (BACKEND / ".env.example").read_text(encoding="utf-8")
        value = re.sub(r"(?m)^SECRET_KEY=.*$", "SECRET_KEY=" + secrets.token_urlsafe(64), template)
        with (BACKEND / ".env").open("x", encoding="utf-8", newline="\n") as target:
            target.write(value)
        return {"ok": True}
    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)
    import environ
    environ.Env.read_env(BACKEND / ".env", overwrite=False)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    if os.environ["DJANGO_SETTINGS_MODULE"] != "config.settings.local":
        raise RuntimeError("启动器仅用于 config.settings.local；正式环境请使用部署流程")
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from django.db import connections
    from django.db.migrations.executor import MigrationExecutor

    call_command("check", stdout=io.StringIO(), stderr=io.StringIO())
    connection = connections["default"]
    config = connection.settings_dict
    engine = config["ENGINE"].split(".")[-1]
    label = "default / " + engine
    missing = False
    if engine == "sqlite3":
        path = Path(config["NAME"]).resolve()
        if str(config["NAME"]) == ":memory:":
            raise RuntimeError("启动器不支持跨进程内存SQLite，请配置文件数据库")
        try:
            label += " / " + path.relative_to(ROOT).as_posix()
        except ValueError:
            label += " / 外部文件 " + path.name
        missing = not path.exists()
        if not missing:
            # Check real migration history without opening the Owner database writable.
            config["NAME"] = path.as_uri() + "?mode=ro"
            config["OPTIONS"] = {**config.get("OPTIONS", {}), "uri": True}
    else:
        label += " / " + str(config.get("HOST", "")) + "/" + str(config.get("NAME", ""))
        if engine == "postgresql":
            config["OPTIONS"] = {**config.get("OPTIONS", {}), "connect_timeout": 5}
    if missing:
        return {"ok": True, "database": label, "pending": ["首次初始化（现有迁移）"], "admin": False}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        executor = MigrationExecutor(connection)
        executor.loader.check_consistent_history(connection)
        pending = [f"{migration.app_label}.{migration.name}" for migration, _ in
                   executor.migration_plan(executor.loader.graph.leaf_nodes())]
        admin = False if pending else get_user_model().objects.filter(is_active=True, is_staff=True).exists()
        return {"ok": True, "database": label, "pending": pending, "admin": admin}
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = main()
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        # Database exceptions may include connection details; do not stringify them.
        hint = str(exc) if isinstance(exc, RuntimeError) else "请检查本地配置、依赖及数据库连接。"
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": hint}, ensure_ascii=False))
        sys.exit(1)
