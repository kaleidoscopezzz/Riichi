#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
echo '启动服务；不会执行数据库迁移或初始化管理员。'
compose config --quiet
compose up -d --wait --wait-timeout 120
compose ps
