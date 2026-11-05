#!/usr/bin/env bash
# Container-side variables must not expand on the host.
# shellcheck disable=SC2016
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
[[ "$#" -eq 2 ]] || { echo '用法：restore.sh 可信备份.dump 新验证数据库名' >&2; exit 1; }
archive="$1"
target="$2"
[[ -f "$archive" && -s "$archive" ]] || { echo '备份不存在或为空。' >&2; exit 1; }
db_identity
# Never overwrite the configured live DB. Only fresh restore namespaces allowed.
[[ "$target" =~ ^[a-z_][a-z0-9_]{0,62}$ && "$target" == "${DB_NAME}_restore_"* && "$target" != "$DB_NAME" ]] || {
    echo "拒绝目标。必须为新的 ${DB_NAME}_restore_... 验证库，禁止覆盖当前库。" >&2; exit 1;
}
exists="$(compose exec -T db sh -eu -c 'psql -X -U "$POSTGRES_USER" -d postgres -At -v ON_ERROR_STOP=1 -c "SELECT datname FROM pg_database"' </dev/null)"
while IFS= read -r name; do
    [[ "$name" != "$target" ]] || { echo '目标库已存在，拒绝覆盖。' >&2; exit 1; }
done <<< "$exists"
echo "将执行备份中的 SQL 到新库 ${target}；仅可使用自己信任的备份。当前业务库保持不变。"
confirm "RESTORE $target"
compose exec -T db pg_restore --list < "$archive" >/dev/null
compose exec -T db sh -eu -c 'exec createdb -U "$POSTGRES_USER" -O "$RIICHI_DB_USER" "$1"' sh "$target"
if ! compose exec -T db sh -eu -c 'exec pg_restore -U "$POSTGRES_USER" --role="$RIICHI_DB_USER" --dbname="$1" --no-owner --no-privileges --exit-on-error --single-transaction' sh "$target" < "$archive"; then
    echo '恢复 FAILED；保留新目标库用于诊断，业务库未改动。' >&2
    exit 1
fi
printf '%s 恢复 SUCCESS；目标=%s。须验证计数、关联、迁移与业务，再由 Owner 决定切换。\n' "$(date -u +%FT%TZ)" "$target"
