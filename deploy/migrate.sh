#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
compose up -d --wait --wait-timeout 120 db
db_identity
compose run --rm --no-deps -T api python manage.py showmigrations </dev/null
bash "$DEPLOY_DIR/backup.sh" </dev/null
compose run --rm --no-deps -T api python manage.py migrate --plan </dev/null
echo '请核对备份成功、迁移计划、应用版本和目标；生产更新前须停止写入。'
confirm "MIGRATE $DB_NAME"
compose run --rm --no-deps -T api python manage.py migrate --noinput </dev/null
compose run --rm --no-deps -T api python manage.py migrate --check </dev/null
compose run --rm --no-deps -T api python manage.py check </dev/null
echo '迁移成功；现在可运行 deploy/up.sh 并执行健康及业务检查。'
