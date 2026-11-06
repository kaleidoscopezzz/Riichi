#!/bin/sh
# Literal variable names are the envsubst allowlist, not host shell expansion.
# shellcheck disable=SC2016
set -eu
: "${SERVER_NAME:?Set a single real DNS hostname}"
: "${HSTS_SECONDS:=0}"
: "${HTTPS_PORT:=443}"
case "$SERVER_NAME" in *[!a-zA-Z0-9.-]*|.*|*..*|*.) echo 'Invalid SERVER_NAME' >&2; exit 1;; esac
case "$HSTS_SECONDS" in ''|*[!0-9]*) echo 'Invalid HSTS_SECONDS' >&2; exit 1;; esac
case "$HTTPS_PORT" in ''|*[!0-9]*|0*|??????*) echo 'Invalid HTTPS_PORT' >&2; exit 1;; esac
[ "$HTTPS_PORT" -le 65535 ] || { echo 'Invalid HTTPS_PORT' >&2; exit 1; }
# Public host[:port] for the HTTP->HTTPS redirect; the browser must reach the published port.
if [ "$HTTPS_PORT" = 443 ]; then PUBLIC_AUTHORITY="$SERVER_NAME"; else PUBLIC_AUTHORITY="$SERVER_NAME:$HTTPS_PORT"; fi
export SERVER_NAME HSTS_SECONDS PUBLIC_AUTHORITY
envsubst '${SERVER_NAME} ${PUBLIC_AUTHORITY} ${HSTS_SECONDS}' < /etc/nginx/riichi.conf.template > /tmp/riichi.conf
exec nginx -g 'daemon off;'
