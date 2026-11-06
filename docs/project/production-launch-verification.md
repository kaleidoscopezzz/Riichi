# Linux生产上线验证与交付记录

日期：2026-11-06（Asia/Shanghai）。**第一阶段已通过隔离集成验证。** 最终审查、合并提交和主线状态见 [PR #3](https://github.com/kaleidoscopezzz/Riichi/pull/3) 与 [main CI](https://github.com/kaleidoscopezzz/Riichi/actions/workflows/ci.yml?query=branch%3Amain)。第二阶段等待 Owner 提供新服务器和部署授权。

## 起点、范围和历史边界

- 只读核验本地分支main、HEAD和远程main均为`34d4cbdea89bba81a503f2b476f2e1d69de5d714`；PR #1 Docker部署、PR #2修复/CI已合并，起点工作区干净。当前工作分支`codex/production-launch`。
- Owner最新范围为完成Caddy工程、隔离测试、提交/推送、PR、CI全绿、独立审查、合并main后停止。旧/任何正式服务器均不在本阶段连接范围。既有工程保留继续，不清理掉先前实现。
- 增加Caddy为唯一公网入口，Nginx内部HTTP；增加目标绑定预检/发布与数据完整性验证，扩展CI和隔离真实浏览器，逐文件更新文档。领域规则不扩张，不编辑历史迁移、Tag和证据。
- 不导入本地Owner SQLite，不读取旧QA credentials作为真实账户来源，不重置真实管理员，不生成真实业务数据。第二阶段默认复用服务器数据库；正式环境完整赛事写入不在验收范围，改在QA完成。
- PR #1曾在Linux ARM64 Docker验证PG112/SQLite112、前端94、自签HTTPS与恢复等；PR #2曾在Windows验证SQLite135、前端195等。详见原报告；**这些计数均不是本轮实跑结果**。原main CI即使成功，也不能充当本轮变更CI通过。

## 本轮变更与证据登记

| 子系统 | 变更 | 实际状态／证据 |
| --- | --- | --- |
| Caddy/Compose | 四服务、唯一端口发布、持久卷、内部网络、生产/维护及QA配置 | Linux Docker QA 通过，公信 ACME 待上线验收 |
| Nginx/Django | 精确 Caddy IP、原 TCP 对端验证、代理头规范化、真实 IP 限流、生产容器不加载 dotenv | 双客户端和伪造头回归通过 |
| 发布/迁移 | 预检、目标绑定发布、备份、新库恢复、迁移演练、兼容镜像回滚 | 空库首次发布、升级、漂移拒绝及不同镜像 ID 回滚通过 |
| CI/浏览器 | 双库回归、前端、容器和真实 Chromium | 分支与 PR 的六项任务通过，截图见 CI 产物 |
| 文档 | 当前授权、基线、架构和操作手册 | 文件及链接检查通过，历史报告保留 |

## 实际命令、环境与结果

下表登记本轮实跑。容器、代理、迁移、恢复与浏览器的执行入口为 `bash deploy/tests/run_ci.sh`，完整命令见[操作手册](../deployment-linux.md)。

| 检查 | 本轮实际命令／环境 | 结果 | 证据 |
| --- | --- | --- | --- |
| 仓库起点 | `git status --short --branch`、`git rev-parse HEAD`、`git ls-remote origin refs/heads/main`；Windows PowerShell | 已核实起点干净与main一致 | 本轮工具记录；SHA见上 |
| Django SQLite check/migrate/makemigrations/全量 | Python 3.13.18 / Django 5.2.18，独立 SQLite；`check`、`migrate --noinput`、`makemigrations --check --dry-run`、`test --noinput` | PASS，145 项 | `.verification/production-launch/backend/summary-final.json`、`all-tests-final-rerun.log` |
| Django PostgreSQL全量与0005/0006旧列保护 | GitHub Actions Ubuntu / PostgreSQL 17；`manage.py test --settings=verification.postgres --noinput`、`python -m verification.postgres_migration_check` | PASS，145 项；旧列、CHECK、释放原因和幂等重跑通过 | [Linux 作业与产物](https://github.com/kaleidoscopezzz/Riichi/actions/runs/42174604177) |
| typecheck/Vitest/build/npm audit | `npm run typecheck`、`npm test`、`npm run build`、`npm audit --audit-level=high`，另执行 E2E TypeScript 检查 | PASS，195 项 Vitest，审计 0 漏洞 | `.verification/production-launch/frontend/` |
| Compose/ShellCheck/配置语法 | `shellcheck`、`docker compose config --quiet`、`caddy validate`、`nginx -t` | PASS，含生产与维护 Caddy 配置校验 | [PR CI](https://github.com/kaleidoscopezzz/Riichi/actions/runs/42174610185) |
| 容器构建、四服务健康与持久化 | 隔离 `compose build`、启动、restart/recreate | PASS，PostgreSQL 数据、Caddy QA 根证书和站点证书保留 | `operations-summary.json` |
| 代理头/真实IP/Session/CSRF/限流 | `qa_runtime.py`、`verify_proxy.py` | PASS，含 Host/SNI、伪造头、非可信内部对端、双客户端限流、Cookie、CSRF | `http-summary.json`、`operations-summary.json` |
| QA完整赛事/API与真实浏览器 | `npm run test:e2e`，Chromium，通过真实 UI/API | PASS，4/8/12/16 人、1/3/2/6 轮及作废、完赛、320/390/1440 像素深浅主题 | `production-launch-qa` 截图及作业日志 |
| 备份/新库恢复/迁移/发布安全拒绝 | `verify_operations.py`、`release.sh prepare/apply --qa`、`rollback.sh --qa` | PASS，空库首次发布、升级、配置漂移拒绝、备份恢复一致及不同镜像 ID 回滚 | 作业日志、`operations-summary.json` |
| Windows 启动器保留回归 | CI Windows PowerShell 5.1 解析、BOM 和 C# 编译 | PASS，静态 | [PR CI](https://github.com/kaleidoscopezzz/Riichi/actions/runs/42174610185) |
| 文档初检 | `git diff --check`；修改文档Markdown相对链接存在性检查；生产目标/本机绝对路径搜索 | PASS，仅本次文档初检；最终全集安全检查待执行 | 本轮工具输出，无断链/命中 |
| 目标地址、敏感文件及 diff | 检查本轮新增内容、暂存路径与 `git diff --check` | PASS | Git 检查，无目标地址、私钥或运行配置纳入 |

## GitHub、独立审查与交付基线

| 项目 | 当前实际状态 |
| --- | --- |
| 任务分支 | `codex/production-launch` |
| 起点main | `34d4cbdea89bba81a503f2b476f2e1d69de5d714` |
| 已验证候选／PR | `3cef736941d3825e1d67b2926cf646251e9ee31c`，[PR #3](https://github.com/kaleidoscopezzz/Riichi/pull/3) |
| 本轮 GitHub Actions | [分支 CI](https://github.com/kaleidoscopezzz/Riichi/actions/runs/42174604177) 与 [PR CI](https://github.com/kaleidoscopezzz/Riichi/actions/runs/42174610185) 均为 6/6 |
| 独立审查与发现闭环 | 核对了非 root 清单读取、实际配置与镜像绑定、数据库卷身份、回滚条件、入口漂移和 QA 隔离；修复后复核，最终结论以 PR 为准 |
| 合并后 main SHA／CI | 以 [PR 合并记录](https://github.com/kaleidoscopezzz/Riichi/pull/3) 和 [main CI](https://github.com/kaleidoscopezzz/Riichi/actions/workflows/ci.yml?query=branch%3Amain) 为准 |
| 正式服务器部署SHA | 未部署；第二阶段未授权 |

不把包含报告的提交SHA写成自身内容以避免自引用；最后报告或后续追记登记已产生的候选/合并SHA。不得强推或绕过CI/保护规则。

## 失败、阻塞与UNVERIFIED

- 早期失败已保留在 Actions。固定地址被动态分配占用见 [首次运行](https://github.com/kaleidoscopezzz/Riichi/actions/runs/42173583680)，Host/SNI 拒绝见 [第二轮](https://github.com/kaleidoscopezzz/Riichi/actions/runs/42173892316)，Docker 默认网络的空 IPAM 列表见 [第三轮](https://github.com/kaleidoscopezzz/Riichi/actions/runs/42174377198)。最终通过的运行保留这些断言。
- `check --deploy` 在 `HSTS_SECONDS=0` 的初始配置下报告 `security.W004`，其余检查通过。启用或延长 HSTS 的流程见操作手册。
- 第二阶段整体UNVERIFIED且当前不执行：新服务器安装/盘点/端口/卷/磁盘/防火墙、DNS/CAA、真实Let's Encrypt签发与续期、正式数据库迁移/恢复切换、生产管理员登录、线上Cookie/CSRF/核心页面、监控/备份定时任务及长期运行。
- 管理员密码依然由Owner在明确初始化时交互输入；已有有效账号不重复初始化改密。生产只读验收不得用QA凭据冒充真实Owner。
- 本地Owner SQLite和真实业务数据导入不属本轮范围。F0-06历史Tag含义保持原记录，不随工程合并重新判定。

公开证据仅使用仓库相对路径并脱敏；真实.env、主机地址、密钥/证书私钥、cookie、凭据、备份dump、私有发布manifest/receipt与数据库内容留在忽略存储，不提交GitHub。
