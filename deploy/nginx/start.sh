#!/bin/sh
# shellcheck disable=SC2016
set -eu
: "${SERVER_NAME:?Set a single real DNS hostname}"
: "${CADDY_PROXY_IP:?Set the exact Caddy proxy IPv4 address}"
case "$SERVER_NAME" in *[!a-zA-Z0-9.-]*|.*|*..*|*.) echo 'Invalid SERVER_NAME' >&2; exit 1;; esac
# Injection-safe exact IPv4 only; preflight checks subnet membership/collisions.
case "$CADDY_PROXY_IP" in ''|*[!0-9.]*|.*|*..*|*.) echo 'Invalid CADDY_PROXY_IP' >&2; exit 1;; esac
old_ifs="$IFS"
IFS=.
# Deliberate splitting of the validated digits/dots value into four octets.
# shellcheck disable=SC2086
set -- $CADDY_PROXY_IP
IFS="$old_ifs"
[ "$#" -eq 4 ] || { echo 'Invalid CADDY_PROXY_IP' >&2; exit 1; }
for octet do
    case "$octet" in ''|????*|0[0-9]*) echo 'Invalid CADDY_PROXY_IP' >&2; exit 1;; esac
    [ "$octet" -le 255 ] || { echo 'Invalid CADDY_PROXY_IP' >&2; exit 1; }
done
export SERVER_NAME CADDY_PROXY_IP
envsubst '${SERVER_NAME} ${CADDY_PROXY_IP}' < /etc/nginx/riichi.conf.template > /tmp/riichi.conf
exec nginx -g 'daemon off;'
