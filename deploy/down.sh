#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
echo '停止当前 Compose 服务，保留容器和数据卷。'
compose stop
