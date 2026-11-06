# Linux Docker Compose 生产部署

Riichi 使用单机 Nginx + Gunicorn/Django + PostgreSQL。仅 Nginx 发布 80/443；前端为 Vite 构建的静态资源，API 同源 `/api/v1/`，保留 Session/CSRF。API 与数据库分别通过内部 web/data 网络连接，PostgreSQL 数据在 Compose 命名卷中。

本轮实测范围及失败记录见[验证报告](project/docker-production-verification.md)。自签证书的隔离 HTTPS 验证不代表真实域名、CA 证书或 Ubuntu 生产服务器验收。Owner 数据不会自动导入。

## 1. 主机准备

建议 Ubuntu Server 24.04 LTS，64 位 amd64 或 arm64；系统盘至少 30 GB，并为数据库、日志与备份预留独立容量。起步 2C4G，可按使用量升级 4C8G。配置时间同步、SSH 密钥及主机/云安全组，仅开放受控 SSH 和 80/443。

按 [Docker 官方 Ubuntu 文档](https://docs.docker.com/engine/install/ubuntu/) 安装 Docker Engine、Buildx 和 Compose 插件（Compose >=2.24，支持 `up --wait`）。安装 Docker 的 apt 仓库后，软件包命令为：

```bash
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
docker version
docker compose version
```

安装操作修改服务器系统，应由 Owner 执行；本轮未在 Ubuntu apt 环境执行。Docker 发布端口可能绕过 UFW，须按官方文档检查 DOCKER-USER 和云安全组。Docker 管理权限等同主机高权限，仅授予维护人员。不要在服务器全局安装 Python/npm 应用依赖，构建均在镜像内完成。

将仓库放在团队选定的固定目录，例如 `/srv/riichi`；以下命令在仓库根目录执行。脚本也支持从任意工作目录使用绝对脚本路径调用，路径可含空格。不运行 Windows 启动器。

```bash
git clone https://github.com/kaleidoscopezzz/Riichi.git
cd Riichi
git switch --detach OWNER_APPROVED_FULL_SHA
```

`OWNER_APPROVED_FULL_SHA` 必须替换成 Owner 批准的完整提交；不在运行环境自行合并分支。

## 2. 环境和密钥

```bash
umask 077
cp -n deploy/.env.example deploy/.env
chmod 600 deploy/.env
openssl rand -hex 64
openssl rand -hex 32
openssl rand -hex 32
```

三次随机输出分别填入 `SECRET_KEY`、`POSTGRES_PASSWORD`（应用）和 `POSTGRES_ADMIN_PASSWORD`（维护）。在服务器可信终端生成并编辑，不粘贴到聊天、工单或日志。没有默认密码，不覆盖已有 `.env`。不要 `source deploy/.env`，Compose 自己读取它。环境文件不会进入镜像；掌握 Docker 权限者仍可检查容器环境。

必填配置：

| 变量 | 填写方法 |
| --- | --- |
| SERVER_NAME | Owner 提供的单个真实域名，不含协议、端口、路径或通配符 |
| CSRF_TRUSTED_ORIGINS | 浏览器实际访问的来源：`https://域名`；HTTPS_PORT 不是 443 时写成 `https://域名:端口` |
| SECRET_KEY | 新生成的至少 50 字符随机值 |
| POSTGRES_DB / POSTGRES_USER | 数据库和应用角色名，建议保留小写默认值 |
| POSTGRES_PASSWORD | 新生成的应用数据库密码 |
| POSTGRES_ADMIN_USER / POSTGRES_ADMIN_PASSWORD | 独立维护角色与密码；角色须与应用角色不同 |
| TLS_CERT_DIR | 宿主机证书目录的绝对路径 |
| COMPOSE_PROJECT_NAME | 稳定项目名，决定卷名；更新时不能更换 |
| RIICHI_VERSION | 建议设为本次批准提交的短 SHA，标识本机构建镜像 |

离散数据库参数无需将密码放进 URL。原先显式 `DATABASE_URL` 的独立生产配置仍支持；Compose 使用离散参数。生产拒绝 DEBUG、SQLite、空主机及通配主机，CORS 关闭，只接受明确 HTTPS CSRF 来源。

可指定外部配置和备份目录：

```bash
export RIICHI_ENV_FILE="$PWD/deploy/.env"
export RIICHI_BACKUP_DIR=/srv/riichi-backups
```

这两个变量供脚本使用；手工 Compose 命令必须显式带 `--env-file`。备份目录默认是运行脚本用户的 `~/riichi-backups`（仓库外），强烈建议显式指向另一块盘或会同步到异地的目录；不要放在仓库内（`git clean -xdf` 或重新克隆会删除）或静态资源目录。

## 3. 域名、HTTPS 和代理

Owner 将域名 DNS 指向主机，并提供可信 CA 的 `fullchain.pem` 与 `privkey.pem`。将两个文件放进 `TLS_CERT_DIR`，只读挂载 `/etc/nginx/tls`。Nginx UID/GID 为 101，证书目录应允许该组读取：目录可用 root:101 / 750，私钥 root:101 / 640；结合实际宿主机用户映射核对权限。禁止提交证书私钥。不要直接挂载不可遍历的 ACME 符号链接，提供容器内可读取的完整文件或证书副本。

Nginx 内部监听 8080/8443，宿主机映射 `HTTP_PORT`/`HTTPS_PORT`（默认 80/443）；HTTP 308 跳转到固定配置域名，不使用客户端 Host 构造跳转。HTTPS_PORT 不是 443 时，Compose 把它传给 Nginx，跳转目标为 `https://域名:HTTPS_PORT`；端口须为 1–65535 的整数，否则 Nginx 拒绝启动。此时浏览器 Origin 带端口：Nginx 原样转发含端口的 Host，Django 按同源校验通过，`ALLOWED_HOSTS` 只填域名（比对时忽略端口）；CSRF_TRUSTED_ORIGINS 仍应写成带端口的实际来源，与浏览器地址一致。Nginx 覆盖 X-Forwarded-Proto/For/Host 等头；API 不发布端口，Compose 显式开启 `TRUST_PROXY_HEADERS`。若未来修改网络、接入 CDN 或额外代理，须重新验证信任边界，不直接启用公网 real_ip 信任。

HSTS 默认 `HSTS_SECONDS=0`。HTTPS 稳定后可先设 300，再逐步延长；修改后重建 API/Nginx。Django `check --deploy` 在 0 时报告 W004，属于本次明确保留的初期策略，没有静默安全检查。includeSubDomains/preload 在代码中关闭，未来只有 Owner 明确批准并核对所有子域后才可另行修改。

TLS 证书由外部续期机制维护，续期后核对文件权限并执行：

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml exec nginx nginx -t
docker compose --env-file deploy/.env -f deploy/compose.yaml exec nginx nginx -s reload
```

当前没有自动申请证书或伪造的正式域名。隔离测试使用 prepare_qa.py 生成 localhost 自签证书，由测试客户端显式信任；无需关闭正式 HTTPS 配置。

## 4. 首次初始化、迁移与管理员

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yaml build
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --wait db
```

全新空卷的 PostgreSQL entrypoint 仅初始化数据库和角色。应用角色是数据库所有者，但无 SUPERUSER/CREATEDB/CREATEROLE；维护角色不传给 API。既有卷不会重新初始化或根据新环境变量自动改密，改密应通过受控 SQL 与配置同步完成。

此时数据库尚无 Django 表，API readiness 不能通过。使用一次性 API 容器检查迁移：

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm --no-deps api python manage.py showmigrations
bash deploy/migrate.sh
```

`migrate.sh` 按顺序执行数据库身份显示、showmigrations、压缩备份、migrate --plan，等待 Owner 手动输入 `MIGRATE 数据库名`，再正常 migrate、migrate --check 和 check。备份失败或确认不匹配立即退出。首次空库也备份。不会 fake、回退迁移或删除库。生产更新须先停止写入，见第 7 节。

```bash
bash deploy/up.sh
docker compose --env-file deploy/.env -f deploy/compose.yaml exec api python manage.py init_admin
```

Owner 自己在交互终端输入邮箱和密码；复用现有 init_admin 的账号归属保护。已有有效 admin 时会进入 Django 交互改密；如果仅需启动服务，不重复执行该命令。没有默认管理员口令，不通过环境变量、命令行或旧 credentials.json 传密码。

登录后维护选手和真实物理桌，再创建赛事。不导入示例业务数据。

## 5. 运行检查、日志与会话

```bash
bash deploy/status.sh
docker compose --env-file deploy/.env -f deploy/compose.yaml exec api python manage.py check
docker compose --env-file deploy/.env -f deploy/compose.yaml exec api python manage.py check --deploy
docker compose --env-file deploy/.env -f deploy/compose.yaml exec api python manage.py migrate --check
docker compose --env-file deploy/.env -f deploy/compose.yaml exec nginx nginx -t
docker compose --env-file deploy/.env -f deploy/compose.yaml logs --tail=100 api nginx db
```

使用真实域名访问首页、直接刷新 `/tournaments/...`，检查 `/api/v1/health/` 返回 JSON。不存在的 API 应保持 JSON 404，不能返回 index.html；缺失的 assets 返回 404。容器 readiness 还检查数据库连接及待迁移计划；公开 health 仅代表 liveness。所有容器 `unless-stopped`；unhealthy 状态本身不会触发 Docker 重启，Owner 应监控健康状态、磁盘、备份和证书到期。

Cookie 为 Secure / SameSite=Lax，Session 为 HttpOnly。默认会话 8 小时，可调整 `SESSION_COOKIE_AGE`；读取不无限续期。数据库 Session 定期清理可由 Owner 的服务器维护计划执行：

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml exec api python manage.py clearsessions
```

登录按 Nginx 实际来源 IP 限制 5 次/分钟，允许 5 次突发；超出返回中文 JSON 429 和 Retry-After: 60。共享出口多人可能共同触发限制，应结合真实访问量评估，不依赖可伪造的 X-Forwarded-For。日志输出 stdout/stderr，json-file 每服务 10 MB × 3；访问日志不记录 Cookie、请求体、查询串。不要把完整 `compose config` 或容器环境发到公开日志。

## 6. 备份与恢复

```bash
bash deploy/backup.sh
```

脚本用维护角色执行 pg_dump custom 压缩格式，存宿主机 `RIICHI_BACKUP_DIR`（默认 `~/riichi-backups`，位于仓库外）。若该目录位于仓库内，backup.sh 与 status.sh 会显著警告；默认目录仍与数据库卷同盘，强烈建议指向另一块盘或异地同步目录。`bash deploy/status.sh` 显示当前备份目录和最新备份；旧版本默认的 `deploy/backups` 若仍有备份会提示，需人工复制到仓库外并核对，脚本不移动或删除它们。UTC 时间戳与随机后缀防止覆盖；权限 600，检查退出状态和非空，输出时间、字节数和 SUCCESS/FAILED。不完整文件不会发布为成功备份。镜像重建不影响此目录。由 Owner 配置每天及升级前备份，按恢复点需求制定保留期，并加密复制到异机/对象存储；本仓库不会自动删除旧备份。

在当前服务旁恢复到独立新库，例如：

```bash
bash deploy/restore.sh "${RIICHI_BACKUP_DIR:-$HOME/riichi-backups}/CHOSEN_BACKUP.dump" riichi_restore_check
```

替换成实际备份文件。必须输入 `RESTORE riichi_restore_check`。脚本只允许当前库名加 `_restore_...` 的新库；拒绝当前业务库、既有目标及不可信名称。pg_restore 在单事务中恢复，遇错停止；失败时保留目标用于诊断，不删除数据库。只恢复自己信任的备份，因为恢复会执行其中 SQL。

对恢复库使用一次性 API，核对迁移与只读清单：

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm --no-deps -e POSTGRES_DB=riichi_restore_check api python manage.py migrate --check
docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm --no-deps -e POSTGRES_DB=riichi_restore_check api python -m verification.data_manifest
```

恢复前后在停止写入的相同代码/迁移版本生成 manifest，应对比所有模型的 count/hash 和零 FK 孤儿，并抽查成绩、冠军、历史桌及会话/管理员访问。确认后由 Owner 决定是否停机切换 `.env` 中 POSTGRES_DB 指向验证过的新库，保留旧库和备份；脚本不提供覆盖生产库的快捷选项。切换后重建 API/db 容器以同步配置，既有卷不会因为库名配置改变而自动新建空库。

## 7. 更新、停止与重启

更新安排维护窗口，通知使用者并停止写入：

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml stop nginx api
bash deploy/backup.sh
git fetch origin
git switch --detach OWNER_APPROVED_FULL_SHA
docker compose --env-file deploy/.env -f deploy/compose.yaml build
docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm --no-deps api python manage.py migrate --plan
bash deploy/migrate.sh
bash deploy/up.sh
```

记录旧/新 SHA、镜像、迁移状态、备份位置及验证结果。复用原 COMPOSE_PROJECT_NAME 和卷，不在更新时改数据库大版本或轮换密码。回滚应用前确认 schema 向后兼容；涉及不兼容变更时恢复到独立库验证，由 Owner 决策，不自动逆迁移。PostgreSQL 大版本升级是单独备份/恢复或 pg_upgrade 工程，不能直接改 image 后启动旧卷。

```bash
bash deploy/down.sh
bash deploy/up.sh
docker compose --env-file deploy/.env -f deploy/compose.yaml restart
```

down.sh 只 stop，保留数据卷。常规操作严禁 `down -v`，也不清理卷或全局 Docker 资源。变更环境变量须 `up -d` 重建，restart 不加载新环境。

## 8. SQLite → PostgreSQL 历史迁移计划

本轮不读取或迁移 Owner SQLite。未来迁移必须另安排停写窗口、人工批准，并先在副本演练。

1. 记录源代码 SHA、迁移图和实际源库；停写后用 SQLite 在线 backup API 生成一致副本并校验，保留原库，只对副本运行检查。源和目标必须是同一代码及已确认迁移版本。
2. 在副本选择 local settings，执行 check / showmigrations 和 `python -m verification.data_manifest`。该工具输出全部模型计数、字段规范化 SHA256 和 FK 孤儿数，不输出密码散列或业务记录。
3. 创建独立 PostgreSQL 目标，正常 migrate 至相同版本。导出逻辑 fixtures（UTF-8）：`python manage.py dumpdata --all --indent 2 --output EXPORT.json`。保留主键，不使用 natural-primary 改写身份；备份文件按敏感数据管理，不能提交。包含 auth、contenttypes 时需与相同迁移版本生成的内容精确对齐，不用 flush 清库。
4. 在独立新目标用 `python manage.py loaddata EXPORT.json` 单事务装载。Django raw=True 不触发新建 PlayerProfile 信号，避免生成平行档案。已有 contenttypes/permissions 主键冲突必须在演练阶段核对版本、映射与唯一键，遇错停止，不能用删库/fake 掩盖。循环 FK（Tournament.champion → Participant → Tournament）依靠 PostgreSQL 可延迟 FK 在事务末校验；不禁用业务约束。
5. 核对 PostgreSQL sequence 已至少达到各表 max(pk)，可审查 `sqlsequencereset accounts players machines tournaments auth contenttypes sessions` 输出后执行。验证下一次新增身份不冲突。JSON 中的分子/分母、数字字符串、昵称快照、首轮顺序和审计字段逐字段规范化比对，不使用 float 转换。JSONB 键顺序不算差异。
6. 对目标再次执行 manifest，与源副本相同模型的 count/hash、M2M 值和零孤儿对比；检查迁移状态，运行管理员登录、历史只读、在新测试赛事上完成录分/完赛；核验约束、外键、设备占用、自动释放以及精确排名。
7. Owner/Planner 复核后才切换正式应用。可丢弃源 Session 并强制重新登录仅在 Owner 单独批准后进行；若保留 Session，需保留 SECRET_KEY 并核验有效期。保留源只读备份和切换时间。发生任何差异停止切换。

实际业务实体清单：accounts.User（含 groups/user_permissions）、players.PlayerProfile、machines.MahjongMachine、tournaments.Tournament、TournamentParticipant、TournamentRound、RoundTable、RoundSeat、MachineAllocation、TournamentTable、TournamentMachineReservation、TableResult、LotteryRecord，及 auth.Group/Permission、contenttypes.ContentType、sessions.Session。包括机器 legacy capacity_slot、旧分配桥、rules/version/source、精确成绩/确认审计、公开抽签、champion/final_snapshot/completed_at/by；不可只搬活跃赛事或当前选手。`django_migrations` 由目标正常 migrate 产生，另比对迁移图，不用复制源 SQLite 文件实现迁移。

本方案仍须用实际源数据副本演练；未完成真实数据迁移验收，标记 UNVERIFIED。

## 9. 资源起点和排障

| 主机 | API | PostgreSQL | Nginx |
| --- | --- | --- | --- |
| 2C4G | 2 sync workers，768 MB，1 CPU | 1 GB，shared_buffers=256MB，max_connections=40，1 CPU | 128 MB，0.5 CPU |
| 4C8G | 3 workers，1.5 GB，2 CPU | 2 GB，shared_buffers=512MB，max_connections=60，1.5 CPU | 256 MB，0.5 CPU |

变量在 .env.example；这些是起点，CPU 配额总和可超过物理核数，实际按同时访问量、数据库大小和压力测试调整。本轮没有压测，不宣称吞吐或延迟保证。保留主机内存给系统、文件缓存和备份。无需 Redis/Celery。观察 `docker stats`、数据库连接数、OOM 和慢请求后调整。

常见问题：

- API unhealthy：先看 api/db 日志，确认库可连接、迁移已完成；公开 health 成功不能证明数据库就绪。
- TLS 启动失败：检查真实文件、完整证书链及 101 的读取权限；证书目录不存在时配置拒绝自动创建。
- 403 CSRF：检查浏览器域名/端口与 CSRF_TRUSTED_ORIGINS，Secure Cookie 是否送达，代理头是否覆盖，Nginx 是否仍转发含端口的 Host；不要关闭 CSRF。
- HTTP 跳转到打不开的地址：确认 `.env` 的 HTTPS_PORT 与实际发布端口一致，修改后 `up -d` 重建 nginx。
- 登录 429：等待一分钟，核对共享出口；不要绕过 Nginx 直接暴露 API。
- 数据看似丢失：检查项目名、卷挂载及数据库名，停止写入核对旧卷，禁止删除/重建掩盖问题。
- 端口占用：查明已有服务，调整绑定或维护窗口，不终止无关进程。
- 恢复失败：保留错误日志和新目标；原库不动，检查备份格式、版本、容量和角色权限。

## 10. Ubuntu 隔离复验

仅在空闲 18080/18443 端口运行。prepare 每次新建忽略目录、新项目及卷，禁止将正式 .env 传入 QA 脚本。

```bash
python3 deploy/tests/prepare_qa.py
# 将下面路径替换为上一命令实际输出的目录：
export QA_DIR="$PWD/.verification/docker-qa-REPLACE"
export RIICHI_ENV_FILE="$QA_DIR/.env"
export RIICHI_BACKUP_DIR="$QA_DIR/backups"
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml config --quiet
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml build
bash deploy/migrate.sh
bash deploy/up.sh
python3 deploy/tests/qa_runtime.py --env-file "$RIICHI_ENV_FILE" --ca "$QA_DIR/certs/fullchain.pem" --url https://localhost:18443
python3 deploy/tests/verify_operations.py --env-file "$RIICHI_ENV_FILE" --work-dir "$QA_DIR"
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml -f deploy/tests/compose.qa.yaml run --rm --no-deps api python manage.py test --settings=verification.postgres --noinput
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml exec -T api python -m verification.data_manifest > "$QA_DIR/before.json"
bash deploy/backup.sh
# 选取刚生成的实际备份路径，restore 需要输入确认字符串：
bash deploy/restore.sh "$QA_DIR/backups/CHOSEN_BACKUP.dump" riichi_qa_restore_check
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml run --rm --no-deps -e POSTGRES_DB=riichi_qa_restore_check api python -m verification.data_manifest > "$QA_DIR/restored.json"
cmp "$QA_DIR/before.json" "$QA_DIR/restored.json"
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml up -d --force-recreate --wait
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml exec -T api python -m verification.data_manifest > "$QA_DIR/recreated.json"
cmp "$QA_DIR/before.json" "$QA_DIR/recreated.json"
bash deploy/down.sh
```

QA 覆盖 4/8/12/16 人、1/3/2/6 轮、负数/零、总和拒绝、确认锁定、重排、抽签、冠军和释放，以及 HTTPS、代理头、API 404、SPA、Session/CSRF、非管理员拒绝和登录限流。QA 会在空 riichi_qa 中生成随机测试管理员，仅该隔离测试脚本可这样建测试身份；正式账号必须使用交互 init_admin。

`verify_operations.py` 仅接受 riichi_qa 和专用 QA 项目名，检查实际拒绝原因，并测试并行备份、恢复内容一致、restart/recreate 持久化、数据库不可用备份失败、任意工作目录、内部网络和角色权限。它保留备份、恢复库与失败日志，不清理数据。生产环境禁止运行该故障模拟工具。QA 备份位于仓库内被忽略的 `.verification`，backup.sh 会输出仓库内警告，属预期；正式环境不要这样放置。

历史迁移可在另一个全新 QA 库中复验（目标已存在时停止，不覆盖）：

```bash
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml exec -T db sh -c 'createdb -U "$POSTGRES_USER" -O "$RIICHI_DB_USER" riichi_qa_legacy'
docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml run --rm --no-deps -T -e POSTGRES_DB=riichi_qa_legacy api python -m verification.postgres_migration_check
```

`compose.qa.yaml` 只用于一次性测试命令，绝不与正式 up 联用。全量 SQLite、前端、备份恢复、防误操作、网络与镜像检查的实跑命令/证据见验证报告。确认后按服务器的实际域名和可信证书另做外网及浏览器验收。
