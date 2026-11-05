#!/bin/sh
# Literal variable names are the envsubst allowlist, not host shell expansion.
# shellcheck disable=SC2016
set -eu
: "${SERVER_NAME:?Set a single real DNS hostname}"
: "${HSTS_SECONDS:=0}"
case "$SERVER_NAME" in *[!a-zA-Z0-9.-]*|.*|*..*|*.) echo 'Invalid SERVER_NAME' >&2; exit 1;; esac
case "$HSTS_SECONDS" in ''|*[!0-9]*) echo 'Invalid HSTS_SECONDS' >&2; exit 1;; esac
export SERVER_NAME HSTS_SECONDS
envsubst '${SERVER_NAME} ${HSTS_SECONDS}' < /etc/nginx/riichi.conf.template > /tmp/riichi.conf
exec nginx -g 'daemon off;'
