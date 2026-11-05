# README 品牌化与 Windows 启动器验证

交付日期：2026-11-05；实际 Windows 日志中的执行时间以各文件为准。本轮只改善仓库呈现、本地环境准备和启停，未修改赛事/计分、API、数据库模型或迁移。

## 起点与 Git 边界

开发前已核对远程 `origin/main`、本地 `main` 和 Owner 已准备的 `feature/windows-launcher-readme` 均为 `c9d7bb87d4c8badb33513a38a147c9a24807c924`，提交说明为 `fix(uat): admin-managed players and unified premium UI`，起点工作区干净。因此满足 UAT-FIX-01 已在 main 的门禁，沿用该任务分支，没有执行 merge、commit、push 或 tag。

F0-01～F0-06 / UAT 原报告、证据和历史迁移不变，不在 README 中展示开发过程或重新宣告正式基线。完整新增/修改清单见[文件清单](windows-launcher-readme-files.md)，最终 Git/安全/链接审计见[审计 JSON](evidence/windows-launcher-readme/audit.json)。

## README 与品牌素材

- 以原创深海军蓝/金色 SVG 标识、四风牌和克制的本地技术徽标替换工作日志式首页。素材为代码绘制，无外部图片、脚本、字体或动画依赖。
- README 分为产品简介、界面预览、功能、技术架构、快速启动、使用流程、目录、开发测试和限制；详细运行说明迁入[本地开发文档](../local-development.md)。保留一处旧锚点供历史链接兼容，没有可见 UAT 缺陷或过程记录。
- 图片为既有真实 QA 应用截图的逐字节副本：`workspace-dark.png` 来自 UAT 下拉整改的最终深色赛事图；`tournaments-light.png` 来自同轮浅色赛事图。未伪造用户、成绩或运营数据，页面明确标注测试资料，图片不含个人账户/电脑信息。
- 未宣称许可证、CI、覆盖率或公网部署。README 所有文件路径相对仓库，不包含开发机绝对路径。
- Chrome 中检查了浅色/深色背景下的本地顶部 HTML 和素材，所有 SVG/PNG 加载成功，见[浅色预览](evidence/windows-launcher-readme/brand-light.png)、[最终深色预览](evidence/windows-launcher-readme/brand-dark-final.png)。这是素材/顶部 HTML 预览，不冒称 GitHub 完整 Markdown 线上渲染。

## 启动器实现

`start.bat` / `stop.bat` 仅调用 Windows PowerShell，保留输出供双击使用者查看。路径由脚本位置推导；PowerShell UTF-8 BOM、bat CRLF，支持中文/空格目录，不请求管理员权限、不改全局执行策略或安装全局运行时。

`scripts/start.ps1` 读取 `.python-version` 和 package.json engines，检查 Python / Node / npm；Python需3.13且不低于仓库补丁版本。复用现有 venv 或现有解释器，依赖核对已锁定元数据，必要时经 `PREPARE` 确认创建 venv、按 requirements.txt 安装、执行 npm ci。缓存与运行日志留在项目内。既有虚拟环境版本不符时拒绝覆盖；有效依赖跳过安装。

无配置时经 `CONFIGURE` 确认从 .env.example 创建随机密钥，不打印或覆盖原文件。沿用现有进程环境优先于.env规则，且只支持开发设置。`launcher_probe.py` 不在探测阶段创建 SQLite 文件，对已有 SQLite 以只读 URI 检查真实迁移图、历史一致性与管理员存在情况。PostgreSQL连接探测设置5秒超时，不输出数据库URL/密码或原始连接异常。迁移前展示目标与待执行项，必须明确输入 `MIGRATE`；非交互/取消均不迁移。管理员仅提示交互 `init_admin`，没有默认密码或自动创建/改密。

后端8000通过health后才启动前端5173，并验证监听端口属于本轮 Job。进程内固定本地代理和前端同源API根，不改.env，避免旧跨域配置将登录请求送往别处。前端就绪后调用默认浏览器，浏览器关联异常时保留健康服务并提示手动地址。

`run.ps1` 是唯一隐藏的运行协调进程，持有匿名 Windows Job Object。`LauncherProcess.cs` 使用 CreateProcessW 以挂起状态创建应用、加入 Job 后才恢复；KILL_ON_JOB_CLOSE 收束其子进程。启动协调进程不继承调用者管道，调用者关闭/重定向输出不会挂住日常启动；后台不用另装框架、服务或计划任务。

停止前校验根目录、随机运行ID、命令行、PID、创建时间及可执行文件路径；使用同一内核句柄重新确认身份并终止协调进程，关闭 Job 后回收本次全部进程。没有按进程名终止或抢占端口。项目命名Mutex防重复启动/停止竞态；状态文件原子替换，读取允许共享删除。进程已退出可清理过期状态，身份不符则拒绝终止并保留现场。正常停止清理 state.json，日志保留。

原理参考 [Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) 与 [CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)，本地验证结果见下表。

## 实际验证

所有写入均在仓库 `.verification/launcher/` 下明确标记的隔离副本，包括中文与空格目录；没有把 Owner 的.env/数据库/密码复制过去。探测、安装、迁移及服务均使用副本。原 Owner `backend/db.sqlite3` 开始与结束 SHA256：`C4738A1EADA032C19A2F9E33F2DCB555A961F1457321B5BD2EBCCD92FFA3A2C9`。

| 项目 | 实际结果 / 证据 |
| --- | --- |
| 全新首次安装 | PASS，Windows PowerShell5.1：创建venv、pip锁定9项、npm ci安装、创建随机配置、明确同意迁移、后端与前端ready；[完整输出](evidence/windows-launcher-readme/first-install.txt) |
| 日常/重复/停止/已退出 | PASS，19项脚本检查中的相应用例，重复启动保留同一owner身份，停止后端口与原进程身份均退出，状态清理；[最终结果](evidence/windows-launcher-readme/smoke-complete/smoke-results.json) |
| 缺 Python/Node/npm | PASS，分别指定不可用工具路径并实际执行脚本，拒绝启动；没有卸载全局工具来制造场景 |
| 8000 / 5173 占用 | PASS，用独立测试监听器占用，启动拒绝且监听器仍存活；未终止占用者 |
| 无迁移同意 / 取消 / 同意 | PASS，前两者不创建新SQLite文件；明确 MIGRATE 后应用原有迁移并正常启动 |
| 数据库不可用 | PASS，仅连接本机关闭的PostgreSQL端口；最终超时修订后8.47秒返回明确错误，[记录](evidence/windows-launcher-readme/database-timeout-final.txt)。这不等同 PostgreSQL 成功连接验证 |
| 后端 / 前端启动失败 | PASS，仅在QA副本注入进程退出/配置异常，验证另一服务回收、端口空闲、日志保留；不修改主仓库业务代码 |
| PID复用/无关命令行 | PASS，用真实无关测试进程 + 陈旧创建时间、再用真实PID时间但不匹配命令行，分别拒绝终止，测试进程存活；属受控复用身份模拟，不冒称强迫Windows实际回收同一个PID |
| 无管理员提示 | PASS，首次和日常输出均提示 init_admin；QA没有创建固定密码管理员 |
| bat入口与自动浏览器 | PASS，包含中文空格目录中由cmd执行批处理；[start](evidence/windows-launcher-readme/batch-start-browser.txt) / [stop](evidence/windows-launcher-readme/batch-stop.txt)。Chrome实际出现本地登录页，[URL/标题记录](evidence/windows-launcher-readme/auto-browser.json)。没有读取或修改现有表单输入 |
| PowerShell7调用 | PASS，实际执行ps1完成ready；入口本身仍以Windows PowerShell5.1为默认。不要求用户安装PowerShell7 |
| 同源API隔离 | PASS，注入外部测试API根，启动后Vite实际注入本地根、代理health正确，[记录](evidence/windows-launcher-readme/local-api-base.txt) |
| Django check | PASS，0 issues，[日志](evidence/windows-launcher-readme/backend-check.txt) |
| makemigrations --check --dry-run | PASS，No changes detected，[日志](evidence/windows-launcher-readme/migrations-check.txt) |
| Django全量 | PASS，108/108，在隔离副本的测试库中执行，[日志](evidence/windows-launcher-readme/backend-tests.txt) |
| TypeScript / Vitest / Vite | PASS，86/86；build内再次typecheck，[类型](evidence/windows-launcher-readme/typecheck.txt) / [测试](evidence/windows-launcher-readme/vitest.txt) / [构建](evidence/windows-launcher-readme/build.txt) |
| diff / 文件 / 忽略 / 凭据 / 链接 | 见[最终审计](evidence/windows-launcher-readme/audit.json)与[文件清单](windows-launcher-readme-files.md) |

版本化的可复现启动器检查为 `scripts/tests/verify_launcher.py`，需要仓库忽略目录下、带 `.launcher-qa` 标记的隔离副本；拒绝对工作仓库执行故障注入。关键命令（从仓库根目录，QA副本需先准备）：

```powershell
backend\.venv\Scripts\python.exe scripts\tests\verify_launcher.py --qa-root ".verification/launcher/中文 路径/Riichi" --evidence docs/project/evidence/windows-launcher-readme/smoke-complete
```

实际启动脚本测试均调用 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1`（或stop），日常自动检查用 `-NoBrowser -NonInteractive`；首次安装通过标准输入提供 PREPARE / CONFIGURE / MIGRATE 三次确认，仅限上述新隔离目录。普通双击不传这些诊断参数。批处理入口通过cmd执行，与资源管理器双击是同一入口；没有将一次人工鼠标双击冒称自动化执行过。

后台全量命令在隔离副本backend执行 `manage.py check`、`makemigrations --check --dry-run`、`test`；前端在主仓库frontend执行 `npm run typecheck`、`npm test`、`npm run build`，这些操作不触碰 Owner 数据库。当前没有新增依赖或改锁文件，完整业务回归结果不是引用旧UAT结果。

## 开发中的失败与修复

- Windows PowerShell5.1会剥离部分native `-c`内嵌引号，已改用不含内嵌字符串引号的版本探测表达式。
- PS5.1 ConvertFrom-Json无法处理npm锁文件的空根键；锁文件元数据改由Node标准库读取，没有添加依赖。
- 从不同PowerShell宿主继承模块路径时Get-FileHash可能不可见，改用.NET SHA256；初期安装输出保留于[诊断](evidence/windows-launcher-readme/diagnostics/install-initial.txt)。其中pip/npm升级提示是第三方安装器输出，未执行全局升级命令。
- PS5.1对.NET null字符串重载及原子替换的文件共享存在兼容问题，改用NullString与FileShare.Delete读取；[初期共享冲突](evidence/windows-launcher-readme/diagnostics/state-sharing-initial.txt)保留。初次失败没有假报启动成功，修订后全新安装及最终19项通过。
- 重定向输出测试发现继承的管道会阻塞调用者退出，协调进程改为原生CreateProcessW无继承句柄启动；不是用延时或忽略超时掩盖。
- 最终故障复查发现协调进程在内核快照与CIM查询之间退出，会保守地留下状态；已添加内核退出重复确认及已退出句柄检查，仍拒绝身份失配的活动进程。[失败记录](evidence/windows-launcher-readme/diagnostics/exit-cleanup-race.txt)保留，修订后最终19项全过，停止同时校验原owner/backend/frontend身份均已退出。
- 初次本机关闭DB端口失败约133秒后返回；探测增加5秒连接超时并单独重测至8.47秒。早期与最终结果分别保留，不覆盖原始运行记录。
- 深色素材第一次截图捕获了未完成绘制帧，`brand-dark.png`保留，仅用重新观察的`brand-dark-final.png`作为最终视觉证据。

## 未验证与交付结论

- **UNVERIFIED**：Owner真实数据库的迁移/管理员初始化与密码输入，本轮没有代为执行；Owner使用前仍需确认自己的数据库与备份。
- **UNVERIFIED**：PostgreSQL成功实连、生产部署、其他Windows版本/另一个标准用户账户、Linux/macOS实际手动运行。当前Windows用户下未请求提权，脚本没有管理员命令。
- **UNVERIFIED**：GitHub提交后的实际页面渲染，本轮无Git发布操作；本地素材/链接检查不等于远程渲染。
- PID复用为实际运行进程上的确定性身份失配测试，未强迫操作系统产生真实PID回收事件。缺工具使用不可用路径验证解析失败，不卸载全局软件。

Developer自检通过：README与脚本行为一致、功能范围未变、Owner数据库未变。所有本轮测试服务及静态预览服务结束后停止，日志与隔离副本在忽略目录保留。保持未提交修改，交由Owner审查与管理Git，不进入下一阶段。
