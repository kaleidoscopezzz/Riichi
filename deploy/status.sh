#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
compose ps --all
latest_dump() {
    find "$1" -maxdepth 1 -type f -name '*.dump' -printf '%T@ %p\n' | sort -nr | sed -n '1s/^[^ ]* //p'
}
printf '备份目录：%s\n' "$BACKUP_DIR"
if [[ -d "$BACKUP_DIR" ]]; then
    warn_backup_location "$BACKUP_DIR"
    latest="$(latest_dump "$BACKUP_DIR")"
    printf '最新备份：%s\n' "${latest:-（无）}"
else
    echo '备份目录尚不存在；运行 deploy/backup.sh 后创建。'
fi
# Backups made under the old in-repo default stay put; never moved or deleted here.
legacy="$DEPLOY_DIR/backups"
if [[ -d "$legacy" && "$(cd -- "$legacy" && pwd -P)" != "$(cd -- "$BACKUP_DIR" 2>/dev/null && pwd -P)" && -n "$(latest_dump "$legacy")" ]]; then
    printf '注意：旧默认目录 %s 仍有备份，请人工复制到仓库外并核对。\n' "$legacy" >&2
fi
