#!/usr/bin/env bash
# Container-side variables must not expand on the host.
# shellcheck disable=SC2016
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
umask 077
receipt=""
if [[ "$#" -ne 0 ]]; then
    [[ "$#" -eq 2 && "$1" == --receipt ]] || { echo '用法：backup.sh [--receipt 新回执.json]' >&2; exit 1; }
    receipt="$2"
    [[ ! -e "$receipt" ]] || { echo '回执已存在，拒绝覆盖。' >&2; exit 1; }
fi
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
# BACKUP_DIR comes from lib.sh (RIICHI_BACKUP_DIR, default ~/riichi-backups).
mkdir -p -- "$BACKUP_DIR"
BACKUP_DIR="$(cd -- "$BACKUP_DIR" && pwd)"
warn_backup_location "$BACKUP_DIR"
temporary="$(mktemp "$BACKUP_DIR/.backup.XXXXXX")"
destination="$BACKUP_DIR/${DB_NAME}_$(date -u +%Y%m%dT%H%M%SZ)_$(basename "$temporary").dump"
compose exec -T db sh -eu -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=6 --no-owner --no-privileges' </dev/null > "$temporary"
[[ -s "$temporary" ]]
# Publish without ever replacing an existing file, even on simultaneous runs.
ln -- "$temporary" "$destination"
if [[ -n "$receipt" ]]; then
    python3 - "$destination" "$receipt" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
archive = Path(sys.argv[1]).resolve()
digest = hashlib.sha256()
with archive.open('rb') as stream:
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(block)
with open(sys.argv[2], 'x', encoding='utf-8') as stream:
    os.chmod(sys.argv[2], 0o600)
    json.dump({'archive': str(archive), 'sha256': digest.hexdigest(), 'bytes': archive.stat().st_size}, stream)
PY
fi
printf '%s 备份 SUCCESS；bytes=%s；%s\n' "$(date -u +%FT%TZ)" "$(wc -c < "$destination" | tr -d ' ')" "$destination"
