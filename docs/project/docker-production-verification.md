# Linux Docker Compose 生产部署交付验证

日期：2026-11-05（Asia/Shanghai）。角色：Developer 自检，等待 Owner / Planner 独立验收。

基线 `4bc28e5b56b6b82c3ef1ad6b2a54e516eb3bc150`；开始时工作区干净，当前 `infra/docker-production` 已由 Owner 准备并与获取后的 origin/main 相同。未修改 main、历史 Tag、业务模型或迁移；附件的新任务明确授权本分支 Commit/Push，取代 AGENTS.md 的上一轮 Bugfix Git 限制。

## 结果与架构

**容器工程及本地 Linux Engine 隔离验证通过；真实 Ubuntu 服务器和公网 HTTPS 上线仍 UNVERIFIED。**

```text
公网 80/443 → Nginx（React dist、TLS、登录限流）
                   ↓ 内部 web 网络
               Gunicorn / Django
                   ↓ 内部 data 网络
               PostgreSQL → 独立命名卷
```

仅 nginx 配置 ports。API UID 10001、Nginx UID 101，均只读根文件系统、丢弃 capabilities；PostgreSQL 官方入口初始化后主进程 UID 999。维护数据库角色与应用角色分开，API 不接收维护密码；应用角色无 SUPERUSER/CREATEDB/CREATEROLE。数据库和 API 无宿主机端口。web/data 为 internal 网络，Nginx 不连接 data，DB 仅连接 data。

启动不执行 migrate、导入数据或创建管理员。迁移脚本备份及显示计划后等待指定确认字符串；恢复只允许新建独立 `_restore_...` 库。down.sh 只 stop；重建与停止均保留命名卷。

实施前审查见[技术差异分析](docker-production-audit.md)。完整变更文件见[文件清单](docker-production-files.md)，部署步骤见[Linux 操作手册](../deployment-linux.md)。README 仅新增一条部署入口。

## 环境、依赖与实际执行

宿主机 macOS ARM64；Docker Desktop 的 **Linux ARM64 Engine 29.8.2**、Compose v5.5.1。使用两个全新命名项目、空卷和 riichi_qa；历史迁移另用全新 riichi_qa_legacy。没有使用 Owner 数据库、旧 QA credentials.json 或 Owner 管理员密码。

生产镜像使用 Python **3.13.18**、Node **22.23.4**、Nginx **1.30.6**、PostgreSQL **17.11**，四个基础镜像均固定 tag 和多架构 digest。Django 5.2.18、DRF 3.18.3、psycopg 3.3.6 沿用原锁。

仅新增生产依赖 **gunicorn==26.2.0**、其传递依赖 **packaging==26.3**，独立 requirements-production.in/txt；没有改变 Windows 使用的 requirements.txt 或前端锁。pip check 通过。没有全局安装依赖、修改主机运行时或 Docker 全局配置。

| 项目 | 本轮实跑结果 | 证据 |
| --- | --- | --- |
| 后端/前端镜像实际构建 | PASS；最终全新 QA 再构建通过 | [build](evidence/docker-production/final-build.log) |
| PostgreSQL、Gunicorn、Nginx 启动/健康依赖 | PASS；三服务 healthy | [up](evidence/docker-production/final-up.log) |
| Django 全量 PostgreSQL | **112 / 112 PASS**；含事务、并发、计分与身份权限 | [PG](evidence/docker-production/final-django-postgres.log) |
| Django 全量 SQLite | **112 / 112 PASS**；临时隔离库 | [SQLite](evidence/docker-production/final-django-sqlite.log) |
| React/Vitest | **94 / 94 PASS，10 文件** | [frontend](evidence/docker-production/frontend.log) |
| TypeScript / Vite build | PASS；Node 测试容器与最终多阶段构建均执行 | 同上及 build |
| npm audit | **0 vulnerabilities** | 同上 |
| Django check、正常 migrate、migrate --check | PASS | [migrate](evidence/docker-production/final-migrate.log)、[check](evidence/docker-production/final-migrate-check.log) |
| makemigrations --check --dry-run | PASS；No changes detected | [迁移一致性](evidence/docker-production/final-makemigrations.log) |
| check --deploy | 退出 0；仅 **W004**，0 silenced | [安全检查](evidence/docker-production/final-deploy-check.log) |
| Compose config --quiet / ShellCheck / bash、sh 语法 | PASS | [命令记录](evidence/docker-production/commands.md) |
| 原启动器依赖锁探针 | 容器已安装依赖与锁完全匹配，ok=true | [probe](evidence/docker-production/frontend-lock-probe-final.log) |
| 镜像敏感文件及最终 Nginx 无 Node/node_modules | PASS | [image safety](evidence/docker-production/final-image-safety.log) |
| Nginx -t、真实 JS/CSS MIME/缓存、HTTP 308 | PASS | [Nginx](evidence/docker-production/final-nginx-check.log)、[静态资源](evidence/docker-production/http-static.json) |
| 真实 HTTPS 赛事/API | PASS；最终 **298 次**请求（含 CSRF） | [HTTPS](evidence/docker-production/final-https-runtime.json) |
| 备份/恢复/重启/重建/保护性拒绝/网络与权限 | PASS；28 项操作及状态检查 | [operations](evidence/docker-production/final-operations-result.json) |
| 历史数据 PostgreSQL 迁移演练 | PASS；旧列逐列一致，旧座次/设备身份不变 | [legacy](evidence/docker-production/postgres-legacy-migration.json) |

W004 是按需求保留的初期 HSTS=0；不通过 SILENCED_SYSTEM_CHECKS 隐藏告警。安全 Cookie、SSL redirect 始终打开，代理头只在明确受信 Compose 拓扑启用；HSTS 子域/preload 关闭。以后 Owner 确认 HTTPS 稳定后调秒数，子域/preload 须另行批准。Session 默认 8 小时；服务日志输出 stdout/stderr，访问日志不记查询串、Cookie 或正文，Docker 日志限制大小。

## 业务、数据库与运维闭环

真实 HTTPS 验证 **4 人 1 轮、8 人 3 轮、12 人 2 轮、16 人 6 轮**，共 4 场、12 轮、37 桌正式成绩。包括负数/零、总和错误拒绝、三人同点有理数计分、确认锁定、后续重排、必要抽签确认、唯一冠军、完赛和物理桌释放。

同时验证管理员登录/退出、Session Cookie 的 Secure/HttpOnly、CSRF Secure Cookie、写入缺 CSRF/恶意 Origin 拒绝、普通用户登录拒绝、公开注册关闭、匿名访问拒绝、真实 API 404 JSON、SPA 深链刷新、缺失 assets 404、点文件拒绝和伪造代理头覆盖。登录限流返回 JSON 429 与 Retry-After，不改变前端。

运维测试实际运行 pg_dump custom 压缩备份、两个并行备份生成独立非空文件、pg_restore 单事务恢复到新库。对恢复前、恢复库、restart 后、force-recreate 后及模拟 DB 不可用再启动后，全部模型的计数、规范化字段 SHA256 和零 FK 孤儿一致。实际拒绝目标为业务库、非法名字、已存在库、EOF/错误确认及损坏备份，并逐项核对拒绝原因。目录不可写或 DB 不可用时备份报告 FAILED；未发布不完整备份。脚本从含中文/空格的任意工作目录调用通过。

历史演练从 tournaments 0002 / machines 0002 的已填充状态正常升级至全部叶节点，核对 5 设备、4 赛事、24 参赛者、3 历史轮次、5 桌、20 座次、5 分配的所有原列（含 updated_at）一致；确认继承有效预留、异常/已释放记录待复核，并测试显式补桌与 historical_only。原 SQLite 专用迁移工具保留不改；新增 PG 工具使用 portable introspection。

SQLite → PostgreSQL 真实数据迁移没有执行；操作手册提供包含全部真实实体、逻辑导出/装载、信号 raw 保护、循环 FK、序列、记录数、逐字段摘要及业务复核的未来计划，仍需源数据副本演练及 Owner 批准。

## 实际失败及修复

保留[失败目录](evidence/docker-production/failures/)与对应成功复跑，不删旧用例或历史证据。

1. Compose flow list 的 tmpfs 逗号未加引号，被解析为多个挂载，API 创建失败。改为单一带引号项，重建和全量测试通过。
2. 迁移前 Compose 调用消费 stdin，指定确认文本提前丢失，脚本安全取消。只读/备份/计划命令关闭 stdin，随后确认与迁移成功；EOF/错误确认另有回归。
3. PostgreSQL 的超长 machine_no 先触发 varchar 类型 DataError，SQLite 由 CHECK 抛 IntegrityError；仅调整原测试的数据库分支预期，保留全部输入用例和业务约束。双数据库完整复跑通过，未改模型或迁移。
4. macOS Bash 3 在变量后紧接中文标点时误解析名称，restore 触发 unbound variable。变量改用花括号，修复库文件同类情况；拒绝测试强化为同时断言错误原因，避免非预期异常被当作正确拒绝。
5. 运维验证器遇 Docker 输出的无效 UTF-8 片段，初次解码失败。诊断读取使用 replacement 并保存日志；脚本正常输出修正后完整复验通过。
6. ShellCheck 首次调用在宿主机展开容器路径 glob；改用明确路径。随后移除未使用变量，为容器内展开/envsubst 的刻意单引号加 SC2016 说明，最终 ShellCheck 退出 0。
7. 本机未安装 frontend/node_modules，直接运行启动器锁探针返回 ok=false。改在已 npm ci 的 Node 构建阶段容器运行，ok=true。未改变探针、源码或依赖锁。
8. CUA 浏览器打开自签 HTTPS 被证书信任拦截，**未绕过**。显式信任测试 CA 的 HTTPS 客户端通过；浏览器验收保留 UNVERIFIED。

## 安全、Git 与未验证事项

已检查真实 QA 密钥未进入候选版本文件；.env、数据库、credentials.json、私钥、dump、虚拟环境和依赖目录均被忽略，示例可版本化。Docker context 使用 allowlist 并排除敏感与生成文件；实际成品镜像扫描通过。没有本机个人绝对路径进入新增文档/证据，证据将仓库/宿主机工具路径前缀规范化为 `${REPO}` / `${HOST_TOOLS}`，去除 ANSI 和行末空白，保留结果和错误。

未修改 backend 历史迁移、业务服务/模型、前端页面或其锁、Windows scripts/start.bat/stop.bat、AGENTS.md、历史报告与验收证据。没有 reset/fake/删库/清卷、真实数据迁移、默认管理员口令或生产账号改密。备份及故障模拟只操作隔离 QA。

**UNVERIFIED：** 真实 Ubuntu 主机安装与服务运行、amd64 实际构建/运行、真实域名 DNS/CA/公网 HTTPS/浏览器界面、证书自动续期、外网防火墙探测、Owner SQLite 数据迁移及正式恢复切换、生产管理员人工初始化、Windows 本轮实机回归、性能/压力/长期稳定性。Docker Linux ARM64 实连和自签 CA 验证不可替代这些项目。2C4G/4C8G 资源仅为起点，没有吞吐保证。

Git 安全检查执行 diff --check / status / diff --stat、忽略与密钥检查；记录见[证据](evidence/docker-production/security-and-git.log)。最终 Commit SHA、origin/infra/docker-production SHA、二者一致性和提交后 clean 状态由最终交付回复提供，避免将提交自身 SHA 写入自身导致自引用。禁止 Tag/merge main/强推，Owner/Planner 的独立验收未被本自检替代。

操作顺序：配置 Owner 密钥/真实域名/证书 → config/build → 仅启动 db → migrate.sh 核对备份/计划并人工确认 → up.sh → 交互 init_admin → HTTPS 与业务验收 → 安排备份/监控。详见完整[部署手册](../deployment-linux.md)。验证完成后停止本次 QA 容器，保留卷、备份及失败数据供复核。

## 后续追记：Caddy生产上线任务（2026-11-06）

本报告保持PR #1候选、三服务Nginx终止TLS及自签隔离验证的原始快照。PR #1/#2已合入main `34d4cbdea89bba81a503f2b476f2e1d69de5d714`，后续生产任务改用Caddy作为唯一公网HTTPS入口。新架构、真实CA/续期和服务器验收以[当前操作手册](../deployment-linux.md)、[生产计划](production-launch-plan.md)与[生产验证](production-launch-verification.md)为准，不把本报告旧轮测试冒称新轮结果。
