#!/usr/bin/env bash
# Container-side variables must not expand on the host.
# shellcheck disable=SC2016
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
umask 077
temporary=""
cleanup() {
    result=$?
    if [[ -n "$temporary" ]]; then rm -f -- "$temporary"; fi
    if [[ "$result" -ne 0 ]]; then
        printf '%s 备份 FAILED（未发布不完整备份）。\n' "$(date -u +%FT%TZ)" >&2
    fi
}
trap cleanup EXIT
db_identity
BACKUP_DIR="${RIICHI_BACKUP_DIR:-$DEPLOY_DIR/backups}"
mkdir -p -- "$BACKUP_DIR"
BACKUP_DIR="$(cd -- "$BACKUP_DIR" && pwd)"
temporary="$(mktemp "$BACKUP_DIR/.backup.XXXXXX")"
destination="$BACKUP_DIR/${DB_NAME}_$(date -u +%Y%m%dT%H%M%SZ)_$(basename "$temporary").dump"
compose exec -T db sh -eu -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=6 --no-owner --no-privileges' </dev/null > "$temporary"
[[ -s "$temporary" ]]
# Publish without ever replacing an existing file, even on simultaneous runs.
ln -- "$temporary" "$destination"
printf '%s 备份 SUCCESS；bytes=%s；%s\n' "$(date -u +%FT%TZ)" "$(wc -c < "$destination" | tr -d ' ')" "$destination"
