#!/usr/bin/env bash
# Disposable Linux QA only. Never sources a production .env or deletes volumes.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
qa_relative="$(python3 deploy/tests/prepare_qa.py | sed -n 's/^QA prepared: //p')"
[[ "$qa_relative" == .verification/docker-qa-* ]] || { echo 'Unexpected QA path' >&2; exit 1; }
qa_dir="$PWD/$qa_relative"
export RIICHI_ENV_FILE="$qa_dir/.env"
export RIICHI_BACKUP_DIR="$qa_dir/backups"
export RIICHI_RELEASE_DIR="$qa_dir/releases"
compose() { docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml "$@"; }
capture_status() {
    result=$?
    compose ps --all > "$qa_dir/container-status.txt" 2>&1 || true
    # No .env, inspect/config output, CA private keys, dumps or credentials in artifacts.
    compose logs --no-color --tail=100 > "$qa_dir/private-container.log" 2>&1 || true
    if [[ "$result" -ne 0 ]]; then echo 'QA failed; private logs and data were retained.' >&2; fi
    exit "$result"
}
trap capture_status EXIT
compose config --quiet
compose build
compose run --rm --no-deps -T caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
compose run --rm --no-deps -T caddy caddy validate --config /etc/caddy/Caddyfile.maintenance --adapter caddyfile
compose run --rm --no-deps -T --entrypoint nginx nginx -V
compose up -d --wait db
printf 'MIGRATE riichi_qa\n' | bash deploy/migrate.sh
bash deploy/up.sh
compose exec -T caddy cat /data/caddy/pki/authorities/local/root.crt > "$qa_dir/qa-root.crt"
python3 deploy/tests/qa_runtime.py --env-file "$RIICHI_ENV_FILE" --ca "$qa_dir/qa-root.crt" --url https://localhost:18443 > "$qa_dir/http-summary.json"
python3 deploy/tests/verify_operations.py --env-file "$RIICHI_ENV_FILE" --work-dir "$qa_dir" > "$qa_dir/operations-summary.json"
compose up -d --wait --wait-timeout 180
compose exec -T nginx nginx -t
compose run --rm --no-deps -T api python manage.py check --deploy
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml -f deploy/tests/compose.qa.yaml run --rm --no-deps -T api python manage.py test --settings=verification.postgres --noinput
compose exec -T db sh -eu -c 'createdb -U "$POSTGRES_USER" -O "$RIICHI_DB_USER" riichi_qa_legacy'
compose run --rm --no-deps -T -e POSTGRES_DB=riichi_qa_legacy api python -m verification.postgres_migration_check > "$qa_dir/migration-summary.json"
# Rehearse the same release safety gates on QA, at this exact committed source.
sha="$(git rev-parse HEAD)"
export RIICHI_VERSION="$sha"
compose build
bash deploy/release.sh prepare --sha "$sha" --output "$qa_dir/release-plan.json" --qa
bash deploy/release.sh apply --manifest "$qa_dir/release-plan.json" --qa
bash deploy/rollback.sh --receipt "$qa_dir/release-plan.receipt.json" --qa
# Browser fixture credentials never leave ignored storage or enter the command line.
compose restart nginx
compose up -d --wait --wait-timeout 120 nginx
python3 deploy/tests/browser_seed.py --env-file "$RIICHI_ENV_FILE" --output "$qa_dir/browser-credentials.json"
export RIICHI_QA_CREDENTIALS="$qa_dir/browser-credentials.json"
export RIICHI_QA_URL=https://localhost:18443
(cd frontend && npm run test:e2e)
echo 'Docker runtime, migration, recovery, release and browser QA PASS.'
