# 本轮实际命令与环境

工作目录为仓库根，路径规范化为 `${REPO}`。全部 QA 配置和数据在忽略目录，不随证据提交。
原项目 `.verification/docker-production`，最终从零复验项目 `.verification/docker-qa-70dc16bc`。
以下变量是命令缩写，不是密码；文件名可在对应日志中核对。除明确列出的初次失败和保护性拒绝，最终命令退出 0。

```bash
QA_DIR="$PWD/.verification/docker-qa-70dc16bc"
export RIICHI_ENV_FILE="$QA_DIR/.env"
export RIICHI_BACKUP_DIR="$QA_DIR/backups"
```

## 镜像、启动、迁移与完整业务

```bash
git fetch origin
git rev-parse HEAD origin/main
git merge-base --is-ancestor 4bc28e5b56b6b82c3ef1ad6b2a54e516eb3bc150 origin/main
docker info --format '{{.ServerVersion}} {{.OSType}} {{.Architecture}}'
python3 deploy/tests/prepare_qa.py
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml config --quiet
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml build
printf 'MIGRATE riichi_qa\n' | bash deploy/migrate.sh
bash deploy/up.sh
python3 deploy/tests/qa_runtime.py --env-file "$RIICHI_ENV_FILE" --ca "$QA_DIR/certs/fullchain.pem" --url https://localhost:18443
python3 deploy/tests/verify_operations.py --env-file "$RIICHI_ENV_FILE" --work-dir "$QA_DIR"
```

自动化确认仅用于本轮明确授权的全新 riichi_qa，正式环境必须由 Owner 人工确认。migrate.sh 实际执行 up db、showmigrations、backup、plan、指定字符串确认、migrate、migrate --check 和 check。详细输出 final-migrate.log。

两轮 HTTPS 流程均通过。最终结果 final-https-runtime.json；运维工具的每一步命令输出在 operations/，28 项结果见 final-operations-result.json。保护性拒绝的退出码 1 是预期结果，同时检查具体拒绝原因，不能只看退出码。

## Django 与前端

```bash
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml -f deploy/tests/compose.qa.yaml run --rm --no-deps api python manage.py test --settings=verification.postgres --noinput
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml run --rm --no-deps -e DJANGO_SETTINGS_MODULE=config.settings.local -e DATABASE_URL=sqlite:////tmp/riichi_qa.sqlite3 api python manage.py test --noinput
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml exec -T api python manage.py check --deploy
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml exec -T api python manage.py makemigrations --check --dry-run
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml exec -T api python manage.py migrate --check
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml exec nginx nginx -t
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml exec -T api pip check
docker build -f deploy/Dockerfile.frontend --target build -t riichi-frontend-test:docker-qa-20261105 .
docker run --rm riichi-frontend-test:docker-qa-20261105 sh -c 'npm run typecheck && npm test && npm run build && npm audit --json'
```

前端测试镜像来自原项目构建阶段，前端源码与锁在整个任务中未变。最终镜像再次实际 npm ci/build（构建缓存可复用）。前端输出 frontend.log；Django 最终双数据库各 112 项通过。

原 Windows 启动器锁探针在已安装依赖的构建阶段复验：

```bash
docker run --rm -v "$PWD/scripts/check_frontend.cjs:/verification/check_frontend.cjs:ro" --entrypoint sh riichi-frontend-test:docker-qa-20261105 -c 'mkdir -p /tmp/launcher/scripts && cp /verification/check_frontend.cjs /tmp/launcher/scripts/check_frontend.cjs && ln -s /app /tmp/launcher/frontend && node /tmp/launcher/scripts/check_frontend.cjs'
```

## 历史迁移、脚本与镜像

在原项目（未停止前）使用其 .env 执行：

```bash
docker compose --env-file .verification/docker-production/.env -f deploy/compose.yaml exec -T db sh -c 'createdb -U "$POSTGRES_USER" -O "$RIICHI_DB_USER" riichi_qa_legacy'
docker compose --env-file .verification/docker-production/.env -f deploy/compose.yaml run --rm --no-deps -T -v "$PWD/backend/verification/postgres_migration_check.py:/app/backend/verification/postgres_migration_check.py:ro" -e POSTGRES_DB=riichi_qa_legacy api python -m verification.postgres_migration_check
bash -n deploy/*.sh
sh -n deploy/nginx/start.sh deploy/postgres/init-app.sh
docker run --rm -v "$PWD/deploy:/mnt:ro" koalaman/shellcheck:v0.11.0 -x -P /mnt /mnt/lib.sh /mnt/up.sh /mnt/down.sh /mnt/status.sh /mnt/backup.sh /mnt/migrate.sh /mnt/restore.sh /mnt/nginx/start.sh /mnt/postgres/init-app.sh
```

历史迁移脚本当时以只读挂载验证；最终 API 镜像已包含同一工具。ShellCheck 最终输出为空、退出 0（shellcheck-final2.log）。SC2016 仅对刻意在容器内展开的单引号字符串及 envsubst allowlist 作带解释的局部文件级说明；未屏蔽 Django 安全检查。

实际 API 镜像遍历 `/app`，断言无 .env、credentials.json、.git、.verification、.venv、node_modules、数据库/私钥/dump；实际 Nginx 成品断言只有 dist，既无 /app 开发目录，也无 node 可执行程序。image-safety.log 记录 PASS。server-users.json 来自读取三服务 `/proc/1/status`，实际主进程分别 UID 10001/101/999。

http-static.json 来自 Python stdlib HTTPS 客户端（显式 cafile，不关闭验证），提取 index.html 的真实 /assets JS/CSS 地址并读取，断言 200、正确 MIME、文件非空及带哈希文件名的一年缓存；同时禁用自动跟随跳转，断言带伪造 X-Forwarded-Proto: https 的 HTTP 请求仍返回固定域名 308。

## 停止、Git 与证据处理

```bash
bash deploy/down.sh
git diff --check
git status --short --branch
git diff --stat
git check-ignore deploy/.env deploy/certs/privkey.pem deploy/backups/test.dump backend/db.sqlite3 backend/.venv/test credentials.json frontend/node_modules/test
```

原项目与最终项目分别使用各自 RIICHI_ENV_FILE 停止。保留全部卷、备份及恢复库；没有 down -v 或全局 prune。Git Commit/Push/远端 SHA 核验在报告完成及安全检查后执行，最终完整 SHA 与 clean 状态在交付回复。

证据从本轮执行日志复制，将仓库/宿主机工具路径前缀替换为 `${REPO}` / `${HOST_TOOLS}`，去除 ANSI 和行末空白，对无效 UTF-8 使用 replacement。未复制 .env、私钥、数据库、fixture 数据、备份或密码。browser.log 为 CUA 工具真实证书错误的文字记录。failures/ 保留实际失败及调用错误，成功结果使用独立文件。
