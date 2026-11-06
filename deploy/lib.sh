#!/usr/bin/env bash
# Container-side variables are intentionally expanded by `sh` inside Docker.
# shellcheck disable=SC2016
# Shared path/Compose handling. Do not source the environment file or use set -x.
set -euo pipefail
DEPLOY_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${RIICHI_ENV_FILE:-$DEPLOY_DIR/.env}"
[[ "$ENV_FILE" = /* ]] || ENV_FILE="$PWD/$ENV_FILE"
REPO_DIR="$(cd -- "$DEPLOY_DIR/.." && pwd -P)"
# Outside the checkout by default: `git clean -xdf` or a fresh clone must never
# delete backups. Prefer another disk or an off-site synced directory.
BACKUP_DIR="${RIICHI_BACKUP_DIR:-${HOME:?未设置 HOME，请设置 RIICHI_BACKUP_DIR}/riichi-backups}"
[[ "$BACKUP_DIR" = /* ]] || BACKUP_DIR="$PWD/$BACKUP_DIR"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "配置不存在：${ENV_FILE}；请按部署文档准备。" >&2
    exit 1
fi
command -v docker >/dev/null
docker compose version >/dev/null
compose() {
    docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/compose.yaml" "$@"
}
db_identity() {
    DB_NAME="$(compose exec -T db sh -eu -c 'printf "%s" "$POSTGRES_DB"' </dev/null)"
    DB_ROLE="$(compose exec -T db sh -eu -c 'printf "%s" "$RIICHI_DB_USER"' </dev/null)"
    [[ "$DB_NAME" =~ ^[a-z_][a-z0-9_]{0,62}$ ]] || { echo '数据库名须为小写标识符。' >&2; exit 1; }
    printf '目标 Compose 数据库：%s；应用角色：%s\n' "$DB_NAME" "$DB_ROLE"
}
warn_backup_location() {
    local real
    real="$(cd -- "$1" && pwd -P)" || return 0
    case "$real/" in
        "$REPO_DIR"/*) printf '警告：备份目录 %s 位于仓库内，git clean -xdf 或重新克隆会删除备份；请把 RIICHI_BACKUP_DIR 指向仓库外，最好是另一块盘或异地同步目录。\n' "$real" >&2;;
    esac
}
confirm() {
    local reply
    printf '需要人工确认，请输入 %s：' "$1"
    IFS= read -r reply || { echo '未收到确认，取消。' >&2; exit 1; }
    [[ "$reply" == "$1" ]] || { echo '确认不匹配，取消。' >&2; exit 1; }
}
