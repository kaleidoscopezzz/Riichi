# 赛事头名赏 Oka 配置验证

日期：2026-11-06。起点为本地及远程main `6b25e0202b633c23d50c8051b209150076c0ff16`，起点工作区干净；本次工作分支为`codex/configurable-oka`。

## 授权与实现

Owner要求允许无头名赏并可配置Oka，随后明确确认：自定义Oka与开局点数、返还原点独立，允许积分合计非零。详细规则已更新至[统一功能规范](../F0-06-functional-spec.md#7-规则配置与版本)。

- 草稿表单支持“自动推导”和“自定义（可为0）”，自定义输入为非负精确十进制，0明确显示“无头名赏”；详情和启动确认显示实际值及模式。
- API新增`oka_override`：省略保持原值，null自动推导，`"0"`明确取消头名赏，`oka`仍只读。值保留精确字符串，后端Fraction计分和并列均分不经过float。
- 新赛事默认规则版本2；旧赛事保留版本1、规则来源和原推导结果。旧草稿明确自定义时原子升级版本，普通读写不自动升级；启动后模式及数值冻结，沿用原revision、权限、Session和CSRF保护。
- 新增`0007_configurable_oka`，仅增加字段/约束并调整新对象的默认值，没有数据回填。0001～0006、历史报告、证据和Tag保持不变。

当前检出没有`backend/.env`或`backend/db.sqlite3`。本轮所有数据库写入使用忽略目录中的独立QA库，浏览器账号/密钥均为本轮新生成的QA值；没有读取旧QA凭据、导入Owner库、连接正式服务器或迁移业务库。

## 本轮环境与结果

Windows / PowerShell 7.6.9；Python 3.13.15 / SQLite 3.53.1 / Django 5.2.18 / DRF 3.18.3；最终前端使用项目内Node 22.23.4及npm 11.19.1；Playwright 1.65.0，Edge（Chromium）156.0.4314.58。既有依赖锁未变更，Node压缩包核对官方SHA256后解压在`.tools`，测试临时文件及缓存均在项目忽略目录。

| 检查 | 实际命令与范围 | 结果 |
| --- | --- | --- |
| Django配置/迁移 | backend内`manage.py check`、`makemigrations --check --dry-run`、`migrate --noinput`，独立`final-checks.sqlite3` | PASS；无系统问题、无遗漏迁移 |
| Django全量 | `manage.py test --noinput` | PASS，158项（含收尾新增的QA数据库入口保护） |
| Oka与历史迁移专项 | `manage.py test tournaments.tests_oka tournaments.tests_migrations --noinput` | 首轮14项PASS；最终改动亦包含在158项全量中 |
| TypeScript | `npm run typecheck`、`tsc --noEmit -p tsconfig.e2e.json` | PASS |
| Vitest全量 | `npm test`，项目内TEMP/TMP | PASS，14文件、201项 |
| 前端构建 | `npm run build` | PASS；保留单个JS块超过500kB的构建提示 |
| 依赖审计 | `npm audit --audit-level=high --registry=https://registry.npmjs.org --cache .cache/npm` | PASS，0漏洞 |
| 备份/恢复/升级 | `.verification/configurable-oka/check_migration.py`调用[迁移演练](../../backend/verification/oka_migration_check.py) | PASS；4个旧赛事、3份确认成绩、1份完赛快照，原列及关系不变；一致备份、独立恢复后升级、幂等重跑通过 |
| 既有真实浏览器流程 | `production-launch.spec.ts`，独立本机HTTPS QA | PASS；4/8/12/16人、1/3/2/6轮、公开抽签/作废、正式完赛、资源释放及320/390/1440深浅主题 |
| Oka真实浏览器专项 | `configurable-oka.spec.ts`，同一隔离QA，另建赛事 | PASS（第三次，31.3秒）；零值/64字符小数保存重读、恢复自动推导、320/390/1440深浅主题、Portal/键盘/Escape/焦点、缺CSRF拒绝、启动冻结及零头名赏完赛闭环 |
| 独立Reviewer | `/root/oka_reviewer`只读检查最终功能差异，另执行400组确定性边界/随机计分交叉校验 | 代码审查PASS；无待修复代码发现；文档版本来源歧义已修正 |
| 安全/范围 | `git diff --check`、`git check-ignore --no-index`及新文件/历史迁移范围检查 | PASS；配置、凭据、数据库、依赖、缓存、构建及trace保持忽略 |

后端命令实际使用既有隔离解释器`D:\Riichi\_tools\cov-venv\Scripts\python.exe`，显式设置`RIICHI_LOAD_DOTENV=False`、随机QA `SECRET_KEY`、`DATABASE_URL=sqlite:///.../backend/.verification/configurable-oka/...sqlite3`及本机允许主机。原始运行日志保存在`backend/.verification/configurable-oka/`；可分享的日志和截图汇总至[本轮证据目录](evidence/configurable-oka)。备份、数据库、Cookie、凭据和浏览器trace不入仓库。

浏览器实际命令为frontend内`npm run test:e2e -- --config=../.verification/configurable-oka/playwright.local.config.ts`；专项复验追加`--output=../.verification/configurable-oka/browser-<轮次> e2e/configurable-oka.spec.ts`。本机配置复用仓库Playwright的localhost HTTPS与QA凭据限制，仅选择已安装Edge及独立输出目录。QA使用隔离Django/SQLite与临时本机TLS静态/API代理，未将其称为Caddy/Nginx/PostgreSQL集成验证。

主要证据：[后端最终158项](evidence/configurable-oka/backend-full-final-qa-guard.log)、[前端201项](evidence/configurable-oka/frontend-full-local-temp.log)、[迁移及恢复摘要](evidence/configurable-oka/migration-summary.json)、[Oka浏览器最终通过](evidence/configurable-oka/browser-third.log)、[安全范围摘要](evidence/configurable-oka/security-summary.json)。既有浏览器用例在首次运行通过，记录见[首次运行日志](evidence/configurable-oka/browser-first.log)，其中也保留当时Oka专项的失败，未将整次首次运行标为PASS。

界面证据：[零头名赏配置](evidence/configurable-oka/oka-zero-config.png)、[零头名赏完赛](evidence/configurable-oka/oka-zero-completed.png)、[320深色下拉](evidence/configurable-oka/oka-select-320-dark.png)、[390浅色精确值](evidence/configurable-oka/oka-custom-390-light.png)。目录中同时保留三种尺寸与深浅主题的全部14张Oka截图；桌面零值、手机展开菜单和长小数截图已人工查看，无横向溢出。

独立Reviewer的400组额外校验在backend内通过`python -c $qaCode`执行内联脚本，未另存脚本：`random.Random(20261106)`，版本1/2各200组，覆盖点数上限、零Oka、64字符整数/小数、随机精确Uma、同点及反转输入顺序；以独立Fraction公式核对奖励、积分、名次、总和及版本1快照结构。仅构造未保存模型，不打开数据库。此400组属于独立审查证据，不混计到Django的158项中。

收尾新增的演练入口在打开连接前拒绝普通数据库：仅接受SQLite内存/`backend/.verification`路径或专用PostgreSQL QA库名`riichi_qa_oka`。本轮实际备份恢复执行的仍是SQLite，专用库名白名单不代表已验证PostgreSQL。

## 保留的失败及处理

1. 初始前端全量14个套件未启动：系统TEMP目录返回EPERM。改为项目内TEMP/TMP后201项通过，原日志`frontend-full.log`保留。
2. 本机默认npm镜像不支持安全审计接口，返回404/NOT_IMPLEMENTED。仅对本次命令指定官方registry，0漏洞；没有修改全局npm配置。原`npm-audit.log`保留。
3. 第一次备份校验用原生sqlite3连接执行`integrity_check`，缺少Django的REGEXP函数；演练脚本改用Django同一组SQLite函数注册。随后恢复计划断言发现QA仅准备了部分应用叶子，补齐sessions基线。两次失败库/备份/日志均保留，最终以全新的隔离文件完成演练。
4. Chromium下载首先遇到系统临时目录EPERM；改为项目内临时目录后下载仍无进展，停止本任务的下载进程，改用已安装Edge（独立浏览器上下文）。没有全局安装浏览器。
5. 首次Oka浏览器验收的全页截图临时改变视口高度，Radix按设计在resize时收起菜单，随后Escape关闭了Sheet。改用视口截图，并保留且加强菜单可见、Escape和焦点回归断言；首次失败截图/日志保留。
6. 第二次专项的手工HTTPS请求带CSRF令牌但漏发Origin/Referer，Django正确返回403。测试请求补齐浏览器实际发送的Origin；缺令牌403与冻结409断言均保留。第二次失败日志保留。

## 未验证及交付边界

- PostgreSQL本轮执行、Linux Docker/Caddy/Nginx集成、GitHub CI、正式数据库和服务器：**UNVERIFIED**。历史其他任务的PASS没有计入本轮。
- 本轮为独立功能分支的本地修改，未提交、推送、创建PR、合并或部署。未触发已完成的上一阶段生产上线任务，也未创建验收Tag。
- 业务库实际应用0007仍需按现有流程先备份、独立恢复核对和检查迁移计划；当前未在业务库执行migrate。
