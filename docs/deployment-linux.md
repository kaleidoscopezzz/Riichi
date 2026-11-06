# Linux Docker Compose生产操作手册

本手册描述可重复执行的生产操作，**不授予当前执行生产变更的权限**。当前只进行第一阶段工程/隔离测试/PR/CI/独立审查/main合并；随后停止。第二阶段等待Owner提供新服务器并明确授权，当前不连接旧服务器或任何正式服务器。实际完成状态见[本轮验证](project/production-launch-verification.md)，任务步骤见[计划](project/production-launch-plan.md)。

## 1. 架构与不变量

```text
公网80/443 → Caddy（Let's Encrypt、HTTP跳转、自动续期）
                 ↓ 内部proxy网络HTTP
             Nginx（React静态资源、API代理、登录限流）
                 ↓ 内部web网络
             Gunicorn / Django
                 ↓ 内部data网络
             PostgreSQL → postgres_data
```

只有Caddy发布宿主机端口并通过edge网络出网；proxy/web/data均internal，Nginx不接数据库网络。Nginx的8080仅业务内网、8081仅容器健康。API和数据库没有宿主机端口；不得为排障临时对公网开放。Caddy的`caddy_data`与`caddy_config`命名卷保存证书、ACME账户和状态，数据库使用既有`postgres_data`。停止/升级不得删卷或修改Compose项目名来误建平行生产数据。

Caddy作为直接公网入口覆盖客户端代理头。Nginx只信任配置的精确Caddy proxy地址，检查原始TCP对端，重写传给Django的Host、X-Forwarded-Proto/For和X-Real-IP。登录限流按验证后的真实客户端IP；不能让所有用户共用Caddy地址或通过伪造头更换限流身份。Django仅在此隔离拓扑启用代理信任，保留HTTPS重定向、Secure Cookie和明确CSRF来源；接入CDN属于新信任边界，须另行审查。

启动不会自动迁移、导入数据或创建管理员。公开health是liveness，API容器readiness还检查数据库与待迁移。`unless-stopped`只处理进程退出；unhealthy本身不会触发Docker重启，需外部监控。

## 2. 第二阶段前置盘点与私有配置

以下操作只在Owner提供新服务器并授权后执行。用已配置SSH认证，先从可信渠道核验主机密钥；不关闭StrictHostKeyChecking，不要求粘贴私钥。记录系统/CPU架构、Docker/Compose、现有服务和80/443占用、现有项目/卷/库、磁盘空间、路由和防火墙。保护非本项目服务；端口冲突不抢占，卷或数据库归属不明时停止。

建议使用受支持Linux、Docker Engine及Compose插件；Python3仅用于标准库运维脚本，应用运行时和依赖全部在镜像内。安装主机软件、修改安全组或防火墙是服务器变更，应包含在第二阶段授权与记录中。云安全组/主机规则仅开放受控SSH与80/443，注意Docker端口发布可能绕过普通UFW规则。

域名A应指向新服务器；存在AAAA时须同样可达，存在CAA时须允许Let's Encrypt。ACME需要公网80/443可达及出站DNS/HTTPS。真实目标只写入私有`.env`和运行参数，不提交到仓库。通过CA验证前不宣称HTTPS上线。

从GitHub取得已审查且CI全绿的正式main完整SHA，在干净checkout运行；先保存旧SHA、镜像和现有配置指纹。不得在生产自行合并分支，不更改数据库主版本。

```bash
# 在已核验的服务器checkout根目录执行；变量由本次运行提供。
# RIICHI_DEPLOY_SHA是已确认的40位main提交，不能用分支名替代。
git fetch origin main
git switch --detach "$RIICHI_DEPLOY_SHA"
test "$(git rev-parse HEAD)" = "$RIICHI_DEPLOY_SHA"
test -z "$(git status --porcelain)"
```

首次配置才从`deploy/.env.example`复制到被忽略的`deploy/.env`，权限600；已有配置不覆盖、不轮换。脚本通过Compose读取env文件，**不要source它或启用set -x**。配置可放checkout外：

```bash
export RIICHI_ENV_FILE="$HOME/riichi-private/production.env"
export RIICHI_BACKUP_DIR="$HOME/riichi-backups"
export RIICHI_RELEASE_DIR="$HOME/riichi-releases"
export RIICHI_VERSION="$RIICHI_DEPLOY_SHA"
```

首次缺少的SECRET_KEY和两个独立数据库密码应由密码学随机源在服务器私有文件生成，不打印到公开日志。重用既有库时沿用原凭据和密钥；环境变量变化不会自动给旧卷改密。不要把管理员密码放.env、命令行或QA凭据中。

| 配置 | 约束 |
| --- | --- |
| COMPOSE_PROJECT_NAME | 复用已盘点的项目名，维持原卷归属 |
| RIICHI_VERSION | 本次完整提交SHA；API/Nginx镜像标签据此选择 |
| SERVER_NAME | 单一真实DNS名，不含协议、端口、路径或通配符 |
| CSRF_TRUSTED_ORIGINS | 实际浏览器HTTPS来源；生产默认443，无跨域CORS |
| SECRET_KEY | 独立高熵值；既有系统不静默更换 |
| POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD | 业务库与应用角色，既有数据时精确沿用 |
| POSTGRES_ADMIN_USER / POSTGRES_ADMIN_PASSWORD | 独立维护角色，仅数据库服务接收，不传API |
| PUBLIC_BIND_IP / HTTP_PORT / HTTPS_PORT | 生产入口80/443，仅Caddy发布；QA另用loopback端口 |
| CADDY_CONFIG / ACME_CA | 生产为Caddyfile和正式Let's Encrypt目录；禁止QA内部CA配置 |
| PROXY_SUBNET / CADDY_PROXY_IP | 专用内部proxy网络与固定Caddy地址；无重叠且地址属于该子网 |
| HSTS_SECONDS | 初期0；稳定后可先300再延长，includeSubDomains/preload保持关闭 |
| SESSION_COOKIE_AGE | 默认28800秒；Secure、HttpOnly Session及SameSite=Lax |
| *_MEMORY_LIMIT / *_CPUS及Gunicorn/DB参数 | 仅资源起点，按主机和运行观察调整，不代表压测保证 |

`RIICHI_ENV_FILE`、`RIICHI_BACKUP_DIR`和`RIICHI_RELEASE_DIR`是脚本运行环境变量；env模板不含真实目标。备份和发布计划位于仓库外，至少权限700目录/600文件；另盘或加密异地副本优于与数据库同盘。不要把完整`docker compose config`、环境或inspect输出发到公开CI日志。

## 3. 首次安装：构建、预检、迁移与管理员

以下手动Compose命令均显式使用同一私有env，不能误读另一项目的配置：

```bash
compose() { docker compose --env-file "$RIICHI_ENV_FILE" -f deploy/compose.yaml "$@"; }
compose config --quiet
compose build
# 只启动已盘点目标db；首次空卷由官方入口正常初始化库和角色。
compose up -d --wait --wait-timeout 120 db
bash deploy/preflight.sh
```

既有卷不会重新初始化。应用角色不具有SUPERUSER/CREATEDB/CREATEROLE；维护角色负责备份恢复。`preflight.sh`只读检查拓扑、生产Caddy配置、端口发布、网络重叠、真实数据库/卷归属和容量，输出脱敏JSON；不检查公网DNS/云安全组，不迁移或创建管理员。原主机路由及非Docker网络也须人工盘点，不能仅依赖Docker网络检查。

执行前需读取计划，核对项目、数据库、OID/卷、env指纹、完整SHA与迁移；默认不从本地Owner SQLite导入数据。首次空库也备份和恢复演练。发布目录位于仓库外，不复用已有manifest文件名：

```bash
bash deploy/release.sh prepare --sha "$RIICHI_DEPLOY_SHA" --output "$RIICHI_RELEASE_DIR/first-install.json"
# 读取私有计划，确认与授权目标及备份/恢复方案一致后执行。
bash deploy/release.sh apply --manifest "$RIICHI_RELEASE_DIR/first-install.json"
bash deploy/status.sh
```

`prepare`要求db已运行、镜像已构建、checkout干净且与所选完整SHA及远程main一致。它不迁移，仅绑定目标身份、env指纹和迁移计划。`apply`为有副作用操作，须在已授权部署窗口运行：再次核对计划/来源，取得项目锁并记录一次性receipt；停止写入，最终备份；恢复到新的`当前库_restore_...`库，比对旧schema投影，正常迁移演练，再比对；原库迁移后与演练完整manifest一致，才启动、退出维护并做健康/公开只读检查。

计划24小时过期、环境/迁移图/库身份漂移、并发锁冲突、已有尝试receipt等均拒绝。失败保留备份、恢复库、私有日志和维护态，不删除数据库，不自动逆迁移或重复apply。查明失败位置和实际写入状态后重新prepare，不删除receipt绕过。

管理员不存在时，由Owner在交互终端运行：

```bash
compose exec api python manage.py init_admin
```

Owner自己输入密码；没有默认口令，不从命令行/环境/旧QA凭据读密码。已有有效管理员时不重复调用，因为会进入改密；已有同名非有效超级管理员时拒绝提权。发布流程永不自动初始化或改密。

如选择原手动迁移入口，保持显式交互：`bash deploy/migrate.sh`先显示真实库、迁移、备份与计划，必须输入`MIGRATE 数据库名`才正常migrate；生产更新仍须事先停写，并自行完成同等恢复演练。不要以手动入口绕过自动发布保护。

## 4. 常规升级、维护与无损回滚

升级前复用原项目/卷/密钥/数据库角色，记录旧SHA和镜像并检查回滚版本兼容。取得新的已合并main SHA、构建、预检，再用新私有manifest执行prepare/apply。不能一边用旧API继续写、一边迁移。单机维护期间返回受控503；禁止外部管理命令同时写入。

需要手工维护时，可在Caddy容器内切换已审查的配置，ACME卷保持不变：

```bash
compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile.maintenance --adapter caddyfile
compose stop nginx api
# 完成经核验的操作后，先确保API/Nginx健康再开放入口。
compose up -d --wait --wait-timeout 180
compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

失败状态先保留维护入口，查私有receipt、容器日志、migrate状态与数据清单。仅当旧代码与当前schema兼容时，选择先前保留的旧应用镜像/SHA并重建服务；不要正常运行逆迁移。0004不可逆，0006复制回填的reverse为noop；因此数据库回退必须走备份恢复到新库的路径，而非migrate到旧编号。

若必须恢复数据：在停写窗口将最后可信备份恢复到新的独立库，核对manifest/迁移/关系和业务历史，复核切换计划后才修改私有配置指向验证库，保留原业务库和所有备份。只有经过授权的切换才能继续；不能覆盖旧库、drop/flush、fake或删卷。切库后重建API及db配置并核对实际库身份；旧卷不会因POSTGRES_DB改变自动创建空库。保留切换前后时间、SHA、旧/新库、备份指纹和结果。

`bash deploy/down.sh`只stop，不删卷。禁止`docker compose down -v`、卷清理/prune或更改PostgreSQL大版本作为修复手段。PostgreSQL主版本升级是独立备份恢复/pg_upgrade工程。

## 5. 备份、恢复与完整性核验

```bash
bash deploy/backup.sh
# 机器可读receipt须位于私有新路径；其内容包含备份路径/校验值。
bash deploy/backup.sh --receipt "$RIICHI_RELEASE_DIR/backup.json"
# 参数为可信archive及全新验证库名；交互输入RESTORE和该库名。
bash deploy/restore.sh "$RIICHI_TRUSTED_ARCHIVE" "$RIICHI_RESTORE_DATABASE"
```

备份使用维护角色pg_dump custom压缩格式、权限600、唯一文件名，检查退出码和非空后发布，不覆盖并发备份。失败不发布不完整文件。目录位于仓库内会警告，旧`deploy/backups`残留只提示，不擅自移动或删除。异地备份传输与保留策略需要服务器运维明确配置，本仓库不自动删除旧备份。

恢复只允许当前库名加`_restore_...`的全新库，拒绝当前业务库、已存在库或非法名称；pg_restore单事务、遇错退出，失败也保留新库供诊断。只恢复可信备份，恢复会执行其中SQL。不要把恢复成功误当业务校验成功。

`verification.schema_manifest`核对源schema中所有旧列的稳定ID、计数、值及关系投影；`verification.data_manifest`比较目标当前模型完整内容和零FK孤儿。0005/0006需在SQLite与PostgreSQL旧数据副本验证：作废默认状态满足CHECK；已释放行release_reason复制旧reason，所有旧列（含reason/updated_at）逐值不变，active行无错误释放信息。发布脚本保存恢复前/后、迁移前/后清单，差异立即停止。

Owner本地SQLite不自动导入。若未来单独授权导入，先做一致副本、同代码/迁移版本的独立PG目标演练，覆盖全部User/Profile/赛事/历史桌座/分配/成绩/抽签/快照/auth/session/序列及循环FK；逐字段规范化比较，不经float、不flush/fake、不更改历史身份。该数据迁移不是本阶段已交付能力。

## 6. HTTPS、会话、线上只读验收与监控

生产使用`Caddyfile`显式ACME issuer及正式Let's Encrypt目录，不手工挂TLS_CERT_DIR，不用`tls internal`。首次真实签发后检查证书SAN、有效期、系统信任链、HTTP→HTTPS、无循环。QA内部CA或本地自签成功不能关闭该验收项。

`caddy_data`与`caddy_config`须持久保留；备份其私钥/账户状态时按敏感数据加密保护。检查Caddy日志中的签发/续期错误、服务器时间、DNS和防火墙，观察真实续期或有实际证据的受控续期验证；不能仅凭配置称续期已实测。证书到期监测应独立于应用health。

```bash
export RIICHI_PUBLIC_URL="https://$RIICHI_SERVER_NAME"
python3 deploy/smoke_production.py --url "$RIICHI_PUBLIC_URL"
bash deploy/status.sh
compose logs --tail=100 caddy nginx api db
```

smoke要求系统信任TLS，禁止不安全模式；只GET检查SPA深链、health、API/assets/点文件404、代理头处理和HTTP跳转，不seed、不登录、不写业务。Owner另用真实浏览器登录并读取赛事/选手/设备，确认Secure/HttpOnly Session、Secure CSRF、正常退出和刷新；拒绝恶意Origin/缺CSRF、非管理员及公开注册。完整赛事流程和限流故障仅在隔离QA，不污染正式统计。

HSTS默认0，Django check --deploy的W004为明确初期策略，不静默屏蔽；HTTPS稳定后可另授权渐进增加，includeSubDomains/preload保持关闭。默认会话8小时，读取不无限续期；可由经配置的服务器维护任务清理过期Session：

```bash
compose exec -T api python manage.py clearsessions
```

运维至少监控：四容器health/退出、公开HTTPS与证书到期、磁盘/inode、DB连接/OOM、备份最近成功/大小/可恢复性及私有日志占用。Docker日志限大小。每天及升级前备份，定期独立恢复演练；具体定时任务、加密异地目标和告警渠道需按实际服务器配置并记录，未配置不能标已完成。资源额度只作为2C4G级主机起点，未做压测不得承诺吞吐/延迟。

## 7. 隔离QA与CI复验

只在专用Linux QA或GitHub Actions运行，禁止指向生产.env/卷：

```bash
bash deploy/tests/run_ci.sh
```

入口生成被忽略的`.verification/docker-qa-*`、独立`riichi_qa`库及项目，loopback18080/18443。QA选择`Caddyfile.qa`/`.qa.maintenance`内部CA，客户端显式信任导出的QA根证书；其私钥、凭据、env、dump、恢复库和失败证据留在私有目录。真实浏览器Fixture只在QA写数据，不使用生产管理员口令。

矩阵包括4/8/12/16人、1/3/2/6轮、负数/零/总和、Fraction、确认锁定、后续分桌、冠军抽签/作废/确认、固定桌释放；代理伪造、直接内部入口、真实IP限流、Session/CSRF/安全头、SPA/404；备份并发、恢复内容一致、restart/recreate持久化、角色/网络隔离和发布目标漂移拒绝。后端SQLite与PG全量、前端typecheck/Vitest/build/audit、ShellCheck/Compose和PS5.1保留回归另在CI执行。

`compose.qa.yaml`只作QA命令覆盖，绝不与正式up联用。故障模拟和凭据生成工具会写QA数据，严禁用于正式环境。CI通过后仍须独立审查，合并main；当前第一阶段到此停止，不连接服务器。所有真实结果、命令、平台限制及失败记录以[本轮报告](project/production-launch-verification.md)为准。

## 8. 常见停止条件

- **端口/资源冲突**：记录归属后停止，不杀其他服务、不改未知卷。
- **preflight拒绝**：按拓扑、子网、真实库/卷、磁盘逐项修复；DNS/宿主机路由/云安全组仍另行验证。
- **API unhealthy**：检查db连接和待迁移；公开health成功不能证明readiness。
- **TLS/ACME失败**：检查A/AAAA/CAA、80/443、出网、系统时钟和持久卷权限；不换内部CA冒充生产，不反复强制申请触发限额。
- **维护态/receipt失败**：保留数据和日志，核对最后成功步骤及真实迁移状态；不删receipt重放、不自动逆迁移。
- **恢复失败/manifest差异**：保留独立恢复库，业务库不覆盖；查可信备份、版本、权限、容量和旧列差异。
- **权限/分支保护**：不能绕过CI或强制他人审查；仅此时请求Owner处理必要权限。
