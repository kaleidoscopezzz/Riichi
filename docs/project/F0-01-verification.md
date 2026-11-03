# F0-01 工程骨架验证记录

- 验证日期：2026-11-03（Asia/Shanghai）。
- 范围：本地工程骨架、健康检查 API、应用外壳与五个基础页面。
- 角色：Developer 自检；Planner 验收尚未完成。
- Git 基线：尚未建立。本任务不得执行 commit、tag、push。

## 验证边界

健康检查是 API 服务存活检查（liveness），不代表数据库、业务功能或生产部署已经就绪。数据库迁移另行验证。本阶段不创建赛事业务模型，不提供注册、认证、分桌或计分功能。界面没有真实或虚构的赛事、选手、成绩记录。

## 实际环境与命令

工作目录为 `D:\Riichi`。所有依赖安装在项目内；没有全局安装项目依赖。

| 项目 | 实际版本 / 路径 |
| --- | --- |
| Python | 3.13.18，`.tools/python/cpython-3.13.18-windows-x86_64-none/python.exe` |
| 虚拟环境 | `backend/.venv` |
| Django / DRF | 5.2.18 LTS / 3.18.3 |
| Node.js / npm | 26.3.0 / 11.16.0 |
| React / TypeScript / Vite | 19.3.1 / 5.9.3 / 8.3.5 |
| Tailwind CSS / Vitest | 4.3.4 / 4.1.12 |
| 开发数据库 | SQLite；仅 Django contenttypes 系统迁移，没有业务模型 |

后端直接依赖记录在 `backend/requirements.in`，全部 9 项依赖精确版本在 `backend/requirements.txt`。前端直接依赖固定版本，完整依赖树由 `frontend/package-lock.json` 锁定。npm 缓存由 `.npmrc` 配置为 `frontend/.cache/npm`。

实际执行的后端命令（工作目录 `D:\Riichi\backend`）：

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py test common config -v 2
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

另执行了生产配置静态检查，临时环境只对该子进程生效，未改写 `.env`、未打印密钥：

```powershell
.\.venv\Scripts\python.exe -c "import os, subprocess, sys, secrets; env = os.environ.copy(); env.update(SECRET_KEY=secrets.token_urlsafe(64), DEBUG='False', ALLOWED_HOSTS='riichi.example', DATABASE_URL='postgresql://localhost/riichi', CORS_ALLOWED_ORIGINS='https://riichi.example'); result = subprocess.run([sys.executable, 'manage.py', 'check', '--deploy', '--settings=config.settings.production'], env=env, capture_output=True, text=True); print(result.stdout, result.stderr); sys.exit(result.returncode)"
```

实际执行的前端命令（工作目录 `D:\Riichi\frontend`）：

```powershell
npm ci
npm run typecheck
npm test
npm run build
npm audit --json
npm run dev
```

`npm ci` 在开发服务启动前成功执行。`frontend-ci.log` 明确标注为该次工具输出的转录；不是后来再次安装的日志。最终测试、构建和审计日志来自真实命令重定向输出。

实际 HTTP 检查使用 `Invoke-WebRequest`，包含直接访问健康接口、带本地/外站 Origin 的响应头检查，以及通过 Vite `/api` 代理访问同一个 Django 接口。

## 验证结果

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| Django 系统检查 | PASS，0 问题 | [check.log](evidence/f0-01/check.log) |
| SQLite 迁移 | PASS，contenttypes 两项迁移成功 | [migrate.log](evidence/f0-01/migrate.log) |
| Django 自动化测试 | PASS，15/15 | [tests.log](evidence/f0-01/tests.log) |
| 迁移完整性 | PASS，`No changes detected` | 执行输出已核实；没有创建业务模型 |
| Python 依赖一致性 | PASS | [pip-check.log](evidence/f0-01/pip-check.log) |
| 生产配置静态检查 | PASS，0 问题；未连接 PostgreSQL | [production-check.log](evidence/f0-01/production-check.log) |
| 实际健康响应 / CORS | PASS，200 JSON、no-store、本地精确放行、外站无允许头 | [http.log](evidence/f0-01/http.log) |
| 前端安装 | PASS，npm ci exit 0 | [frontend-ci.log](evidence/f0-01/frontend-ci.log) |
| TypeScript | PASS，应用及 Vite 配置类型检查通过 | [frontend-typecheck.log](evidence/f0-01/frontend-typecheck.log) |
| 前端自动化测试 | PASS，1 个文件、8/8 | [frontend-tests.log](evidence/f0-01/frontend-tests.log) |
| 前端生产构建 | PASS | [frontend-build.log](evidence/f0-01/frontend-build.log) |
| 前端依赖审计 | PASS，当前锁文件 0 项漏洞 | [frontend-audit.log](evidence/f0-01/frontend-audit.log) |
| Vite → Django 联调 | PASS，真实代理响应与直接响应一致 | [proxy.log](evidence/f0-01/proxy.log) |
| 桌面五页 / 面包屑 / 404 | PASS，真实浏览器导航、页面标题及返回入口正常 | 见下方浏览器记录 |
| 手机五页 / 菜单 / Escape | PASS，320px 五页均无横向溢出；390px 图像复核 | [mobile-routes-final.json](evidence/f0-01/mobile-routes-final.json) |
| 加载 / 错误 / 重试恢复 | PASS，真实服务停止、延迟和恢复实验 | 见下方浏览器记录 |
| 亮暗主题与持久化 | PASS，切换后刷新保留所选主题 | [settings-light.jpg](evidence/f0-01/settings-light.jpg) |
| Git 忽略与敏感信息定向检查 | PASS，环境/依赖/构建/数据库忽略，示例与证据保留 | [git-hygiene.log](evidence/f0-01/git-hygiene.log)、[secrets-check.log](evidence/f0-01/secrets-check.log) |

后端测试覆盖健康 JSON 契约、无数据库查询、HEAD、写方法 405、本地 CORS、外站 CORS、预检、Host 拒绝，以及生产密钥/DEBUG/主机/数据库/HTTPS CORS 安全边界。前端测试覆盖请求契约、HTTP 错误、错误服务/版本/状态、空响应、非 JSON 及网络错误/取消信号。

## 浏览器实测与修正记录

使用本机浏览器连接 `http://127.0.0.1:5173`，API 来自本机 Django，不使用虚构业务数据。检查桌面 1440px、手机 390px 与 320px；访问五个路由，并验证未知路径的 404 与返回仪表盘入口。手机导航点击后等待 URL 和标题完成更新，再判断结果。

1. 直接服务与开发代理正常时显示“服务已连接 / 后端连接正常”。
2. 停止本任务启动的 Django 服务，点击“重新检查”，界面显示“后端服务暂未连接”及启动后重试提示。Vite 的 `ECONNREFUSED` 是该实验的预期结果。
3. 在相同本地端口运行仅用于验证的 WSGI 包装器，将真实 Django 响应延迟 3 秒。点击重试后实际观察到“正在连接 / 正在连接后端服务”、Skeleton、禁用的检查按钮；响应到达后恢复正常。
4. 停止包装器并恢复常规 Django runserver。最终刷新再次连接成功。

延迟包装器实际命令（仅用于本地验证，未加入应用实现）：

```powershell
$env:DJANGO_SETTINGS_MODULE='config.settings.local'
.\.venv\Scripts\python.exe -c "import time; from wsgiref.simple_server import make_server; from config.wsgi import application; make_server('127.0.0.1', 8000, lambda env, start: (time.sleep(3), application(env, start))[1]).serve_forever()"
```

手机初检发现正文/健康反馈为 9～11px，已将主要文字改为 13px、辅助信息 12px，按钮触控高度至少 42px，再次构建并检查。第一次批量导航读取过早，`mobile-checks.json` 中的重复旧标题不作为通过证据；加入 URL/标题等待后，`mobile-routes-final.json` 正确记录五页及 `scrollWidth = 320`。一次 390px 全页截图失败，改用视口截图成功，不影响 DOM 尺寸及导航验证。

开发中热更新一度出现 `useHealth requires HealthProvider`，初始错误证据保留在 [browser-during-development.log](evidence/f0-01/browser-during-development.log)。原因是组件与 Hook 共用导出模块，随后拆分 Provider 和 Context/Hook 边界，并针对两个 Provider 文件更新时间戳（内容 SHA-256 未改变）重新验证热更新。Vite 正常输出两次 HMR update，没有再出现 incompatible export 或整页重载；浏览器错误/警告为空。实现依据 [Vite React 插件的导出约束](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react/README.md#consistent-components-exports)。最终证据为 [hmr-server-final.log](evidence/f0-01/hmr-server-final.log)、[hmr-final-dom.txt](evidence/f0-01/hmr-final-dom.txt) 和 [browser-final.log](evidence/f0-01/browser-final.log)。

截图：

- [最终桌面仪表盘](evidence/f0-01/dashboard-desktop.jpg)
- [手机仪表盘首屏](evidence/f0-01/dashboard-mobile.jpg)
- [手机导航](evidence/f0-01/mobile-navigation.jpg)
- [亮色设置页](evidence/f0-01/settings-light.jpg)
- [后端断开](evidence/f0-01/backend-disconnected.jpg)
- [真实响应延迟时的加载状态](evidence/f0-01/backend-loading.jpg)

shadcn/ui 由官方 CLI 生成，记录及上游 MIT 许可保留。生成阶段 CLI 依赖链曾报告 2 low / 4 moderate；移除非运行依赖 CLI 和重复 `cn` 包后，最终 `npm audit --json` 为 0 项。没有测试或构建失败。密钥扫描初次误报 README 的随机密钥生成命令，人工核对无明文密钥后修正扫描规则，误报记录保留在日志。

## Git 与文件清单

仍为 `main`，尚无 Commit；所有交付文件均为新增未跟踪文件，无暂存内容。origin 未改动，没有执行 commit、tag、push，没有修改远程仓库、重写历史或删除已有仓库文件。

- [最终 Git 状态](evidence/f0-01/git-status.txt)
- [完整新增文件清单](evidence/f0-01/changed-files.txt)
- [源码与文档 SHA-256 清单](evidence/f0-01/source-sha256.txt)，不包含证据目录、自身或本地环境文件；用于候选比对，不构成 Git 基线。

忽略规则使用 `git check-ignore --no-index` 验证，包括 `.tools/`、`.venv/`、`node_modules/`、`dist/`、`.env` 及其本地变体、SQLite 及 sidecar、Python 缓存、测试覆盖率及 collectstatic 输出。`.env.example`、依赖锁和正式证据不被忽略。敏感信息检查针对 Git 可见文本的私钥、GitHub/OpenAI Token 及明文长密钥模式；没有发现明显泄漏，不宣称穷尽所有敏感信息检测。

## 已知限制

- PostgreSQL 实际连接、生产部署、HTTPS 代理和数据库 readiness **UNVERIFIED**，不属于本任务实现范围；生产静态检查通过不能替代这些验证。
- 手机为浏览器视口验证，没有声称在真实手机硬件上测试；浏览器离线事件和完整 8 秒超时路径实现已审阅，未进行系统断网或完整端到端超时实验。
- 两项同分规则及其他异常业务流程仍为 TBD；赛事、账号、选手、设备持久化、分桌、计分及微信模块未实现。
- 本次验证仅使用本机现有 Node.js 26.3.0，没有单独在其他受支持 Node.js 版本上回归。

## 交付状态

Developer 自检结论：F0-01 约定的本地工程骨架验收项目已满足，无已知阻断项。实现与验证结束后停止；本任务拥有的验证服务已关闭。Planner 外部审查尚未完成，首次本地与 GitHub 基线仍为“尚未建立”。
