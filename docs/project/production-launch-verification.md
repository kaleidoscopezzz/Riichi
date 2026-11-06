# Linux生产上线验证与交付记录

日期：2026-11-06（Asia/Shanghai）。**当前状态：第一阶段工程实施中；本轮测试、PR/CI、独立审查与合并尚未登记成功。第二阶段等待Owner新服务器及明确授权，不连接任何正式服务器，不宣称已上线。**

## 起点、范围和历史边界

- 只读核验本地分支main、HEAD和远程main均为`34d4cbdea89bba81a503f2b476f2e1d69de5d714`；PR #1 Docker部署、PR #2修复/CI已合并，起点工作区干净。当前工作分支`codex/production-launch`。
- Owner最新范围为完成Caddy工程、隔离测试、提交/推送、PR、CI全绿、独立审查、合并main后停止。旧/任何正式服务器均不在本阶段连接范围。既有工程保留继续，不清理掉先前实现。
- 增加Caddy为唯一公网入口，Nginx内部HTTP；增加目标绑定预检/发布与数据完整性验证，扩展CI和隔离真实浏览器，逐文件更新文档。领域规则不扩张，不编辑历史迁移、Tag和证据。
- 不导入本地Owner SQLite，不读取旧QA credentials作为真实账户来源，不重置真实管理员，不生成真实业务数据。第二阶段默认复用服务器数据库；正式环境完整赛事写入不在验收范围，改在QA完成。
- PR #1曾在Linux ARM64 Docker验证PG112/SQLite112、前端94、自签HTTPS与恢复等；PR #2曾在Windows验证SQLite135、前端195等。详见原报告；**这些计数均不是本轮实跑结果**。原main CI即使成功，也不能充当本轮变更CI通过。

## 本轮变更与证据登记

| 子系统 | 变更 | 实际状态／证据 |
| --- | --- | --- |
| Caddy/Compose | 四服务、80/443唯一入口、ACME持久卷、内部网络、生产/维护及QA配置 | 实施中，尚未登记成功运行 |
| Nginx/Django | 精确CaddyIP与原TCP对端验证、代理头规范化、真实IP限流、禁dotenv覆盖生产注入 | 实施中，待本轮验证 |
| 发布/迁移 | preflight、prepare/apply、备份receipt、新库恢复/迁移演练、schema/完整manifest保护 | 实施中，待故障与恢复演练 |
| CI/浏览器 | 双DB回归、前端、容器运行/恢复/浏览器矩阵 | 实施中，待当前候选实跑 |
| 文档 | 当前授权/基线、架构、操作手册、计划与此报告；历史仅追加追记 | 实施中，最终diff/链接核对待完成 |

## 实际命令、环境与结果

以下表只登记本轮已执行的结果；拟执行命令见[计划](production-launch-plan.md)与[操作手册](../deployment-linux.md)。初稿未执行测试，不预填通过计数。

| 检查 | 本轮实际命令／环境 | 结果 | 证据 |
| --- | --- | --- | --- |
| 仓库起点 | `git status --short --branch`、`git rev-parse HEAD`、`git ls-remote origin refs/heads/main`；Windows PowerShell | 已核实起点干净与main一致 | 本轮工具记录；SHA见上 |
| Django SQLite check/migrate/makemigrations/全量 | Python 3.13.18 / Django 5.2.18，独立 SQLite；`check`、`migrate --noinput`、`makemigrations --check --dry-run`、`test --noinput` | PASS，145 项 | `.verification/production-launch/backend/summary-final.json`、`all-tests-final-rerun.log` |
| Django PostgreSQL全量与0005/0006旧列保护 | 待执行登记 | UNVERIFIED | 待登记 |
| typecheck/Vitest/build/npm audit | `npm run typecheck`、`npm test`、`npm run build`、`npm audit --audit-level=high`，另执行 E2E TypeScript 检查 | PASS，195 项 Vitest，审计 0 漏洞 | `.verification/production-launch/frontend/` |
| Compose/ShellCheck/配置语法 | 待执行登记 | UNVERIFIED | 待登记 |
| 容器构建、四服务健康与持久化 | 待执行登记 | UNVERIFIED | 待登记 |
| 代理头/真实IP/Session/CSRF/限流 | 待执行登记 | UNVERIFIED | 待登记 |
| QA完整赛事/API与真实浏览器 | 待执行登记 | UNVERIFIED | 待登记 |
| 备份/新库恢复/迁移/发布安全拒绝 | 待执行登记 | UNVERIFIED | 待登记 |
| Windows启动器保留回归 | 待执行登记 | UNVERIFIED | 待登记 |
| 文档初检 | `git diff --check`；修改文档Markdown相对链接存在性检查；生产目标/本机绝对路径搜索 | PASS，仅本次文档初检；最终全集安全检查待执行 | 本轮工具输出，无断链/命中 |
| 最终密钥/忽略/diff | 待最终检查 | UNVERIFIED | 待登记 |

## GitHub、独立审查与交付基线

| 项目 | 当前实际状态 |
| --- | --- |
| 任务分支 | `codex/production-launch` |
| 起点main | `34d4cbdea89bba81a503f2b476f2e1d69de5d714` |
| 本轮最终候选SHA／PR | 尚未登记 |
| 本轮GitHub Actions | 尚未登记，旧main结果不替代 |
| 独立Reviewer与发现闭环 | 待最终候选审查 |
| 合并后main完整SHA／main CI | 尚未登记 |
| 正式服务器部署SHA | 未部署；第二阶段未授权 |

不把包含报告的提交SHA写成自身内容以避免自引用；最后报告或后续追记登记已产生的候选/合并SHA。不得强推或绕过CI/保护规则。

## 失败、阻塞与UNVERIFIED

- 第一阶段最终测试、CI、审查、合并以真实执行补录，目前不能标PASS。失败原始日志保留并关联修复，不删除失败用例或将预期外异常当作安全拒绝。
- 本地若缺Docker/Linux运行环境，可用隔离GitHub Actions Linux执行；尚未执行时仅记环境限制，不声称容器通过。远程CI不代替真实正式服务器。
- 第二阶段整体UNVERIFIED且当前不执行：新服务器安装/盘点/端口/卷/磁盘/防火墙、DNS/CAA、真实Let's Encrypt签发与续期、正式数据库迁移/恢复切换、生产管理员登录、线上Cookie/CSRF/核心页面、监控/备份定时任务及长期运行。
- 曾尝试严格SSH认证时因无可信主机密钥而未执行服务器命令；不关闭主机密钥检查。Owner随后明确第一阶段不连接任何正式服务器，新服务器与主机密钥核验留到第二阶段。
- 管理员密码依然由Owner在明确初始化时交互输入；已有有效账号不重复初始化改密。生产只读验收不得用QA凭据冒充真实Owner。
- 本地Owner SQLite和真实业务数据导入不属本轮范围。F0-06历史Tag含义保持原记录，不随工程合并重新判定。

公开证据仅使用仓库相对路径并脱敏；真实.env、主机地址、密钥/证书私钥、cookie、凭据、备份dump、私有发布manifest/receipt与数据库内容留在忽略存储，不提交GitHub。
