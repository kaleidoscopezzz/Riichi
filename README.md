# Riichi

**轻量级四人立直麻将个人赛事管理系统**，帮助麻将馆管理员快速创建赛事、安排选手、录入成绩、重排座次并决出冠军；物理桌是辅助资源。

正式代码基线为 **F0-05（CLOSED / PASS）**。F0-06完整候选已推送GitHub（`b9e83bb0c8e31ab660b37e7e0a46c1f0bb424e65`），Planner源码/测试证据审查通过，Owner人工验收后正在进行 **UAT-FIX-01** 整改；baseline/F0-06暂未建立。

当前产品仅供雀庄老板/管理员使用。选手由老板新增、编辑、归档或删除，无需本人注册/登录；公开注册API关闭，/register返回登录页，普通账号不能登录后台。完整赛事、精确计分、冠军及自动释放保持F0-06规则不变。

Riichi Premium 界面以深海军蓝、石墨黑和中性色为基础，提供仪表盘、赛事管理、选手管理、麻将机管理和系统设置五个基础页面。仪表盘展示欢迎信息、功能入口与实际后端连接状态，不包含虚构赛事统计。

## 技术栈

- 后端：Python 3.13、Django 5.2 LTS、Django REST Framework。
- 前端：React、TypeScript、Vite、Tailwind CSS、shadcn/ui、Lucide React。
- 数据库：本地 SQLite；正式环境预留 PostgreSQL。
- 架构：前后端分离、模块化单体。

依赖精确版本以 `backend/requirements.txt` 和 `frontend/package-lock.json` 为准。所有依赖和运行资源保留在项目目录内。

## Windows PowerShell 本地启动

需要 Python 3.13、Node.js 22.12 或更新版本及 npm 10 或更新版本。以下命令均从项目路径执行，分别使用两个 PowerShell 窗口运行服务；不需要激活虚拟环境或更改系统执行策略。

后端首次安装（已有 Python 3.13）：

```powershell
Set-Location D:\Riichi\backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

本次工作区已在项目内准备 Python 3.13.18；本机无 `py -3.13` 时，可用以下命令代替创建虚拟环境的那一行：

```powershell
Set-Location D:\Riichi\backend
& ..\.tools\python\cpython-3.13.18-windows-x86_64-none\python.exe -m venv .venv
```

`.tools/` 不进入 Git，新克隆仓库需自行准备 Python 3.13。首次初始化 `.env` 时执行下列命令：读取示例、生成随机密钥并写入本地文件，不在终端打印密钥；已有 `.env` 时会拒绝覆盖，直接复用已有配置即可。

```powershell
Set-Location D:\Riichi\backend
.\.venv\Scripts\python.exe -c "from pathlib import Path; import secrets; text=Path('.env.example').read_text(encoding='utf-8'); Path('.env').open('x', encoding='utf-8').write(text.replace('SECRET_KEY=\n', 'SECRET_KEY=' + secrets.token_urlsafe(64) + '\n'))"
```

不得将 `.env` 提交到 Git。运行时、虚拟环境和依赖均保存在项目内。

初始化并运行后端：

```powershell
Set-Location D:\Riichi\backend
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

前端首次安装并运行：

```powershell
Set-Location D:\Riichi\frontend
npm ci
npm run dev
```

- 应用：[http://127.0.0.1:5173](http://127.0.0.1:5173)
- 健康接口：[http://127.0.0.1:8000/api/v1/health/](http://127.0.0.1:8000/api/v1/health/)

默认前端开发服务器通过 `/api` 代理到本地 Django；健康检查会显示加载、成功或失败状态。请求失败时可检查后端终端及环境配置，然后通过界面重试。

## 验证命令

后端：

```powershell
Set-Location D:\Riichi\backend
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pip check
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/
```

预期健康响应：

```json
{"status":"ok","service":"riichi-api","api_version":"v1"}
```

前端：

```powershell
Set-Location D:\Riichi\frontend
npm run typecheck
npm run test
npm run build
```

上述为复现命令；本轮实际执行及失败/未验证事项以 [F0-06交付报告](docs/project/F0-06-verification.md) 为准，F0-01等旧报告只证明当时版本。生产构建输出到 `frontend/dist/`，开发服务器不能替代生产部署。

## 配置与安全

| 后端环境变量 | 用途 / 本地示例 |
| --- | --- |
| `DJANGO_SETTINGS_MODULE` | `config.settings.local`；正式环境使用 `config.settings.production`。 |
| `SECRET_KEY` | 至少 50 字符的随机密钥；示例留空，未配置会启动失败。 |
| `DEBUG` | 本地 `True`；正式环境必须 `False`。 |
| `ALLOWED_HOSTS` | 本地显式列出 `localhost,127.0.0.1,[::1]`，不接受 `*`。 |
| `DATABASE_URL` | 本地 `sqlite:///db.sqlite3`；正式环境提供私密 PostgreSQL URL。 |
| `CORS_ALLOWED_ORIGINS` | 本地 `http://localhost:5173,http://127.0.0.1:5173`。 |

后端配置拆分为 `base`、`local`、`production`。开发默认 SQLite；PostgreSQL 配置及驱动仅预留，不代表已完成生产数据库验证或部署。生产必须使用独立密钥、关闭 DEBUG、明确允许主机及 HTTPS 跨域来源，并按部署环境配置 HTTPS 和数据库；选择生产设置模块需由进程环境明确提供。

前端无需 `.env` 即可按默认代理联调。需要覆盖时复制 `frontend/.env.example`：`API_PROXY_TARGET` 为 Vite 服务端代理目标，默认 `http://127.0.0.1:8000`；`VITE_API_BASE_URL` 为浏览器公开 API 根地址，留空时请求同源 `/api`。前端环境变量不得包含服务端密钥。`.env`、虚拟环境、`node_modules/`、数据库及构建产物由 `.gitignore` 忽略；示例配置保留版本管理。

## 文档与当前边界

- [需求与已确认规则](docs/requirements.md)
- [开发路线](docs/roadmap.md)
- [架构与目录](docs/architecture.md)
- [基线管理](docs/project/baselines.md)
- [开发约束](AGENTS.md)
- [F0-06完整功能规范（已实现候选，规则已确认）](docs/F0-06-functional-spec.md)

账号、选手、赛事配置/启动与首轮已实现。成绩、精确计分、累计榜、后续分桌、最终冠军/公开抽签和完赛自动释放统一纳入F0-06，不拆F0-07/F0-08。微信、团体赛仍为未来候选，不纳入V1.0。

正式代码基线 `baseline/F0-05`，Commit `41929da1e53f8bb481beb4ea3bc31b65f9ee86ff`，Branch main，Planner CLOSED / PASS；F0-01～05历史基线/报告均保留。D0-01门禁已由Owner确认完成并授权F0-06；本次候选不commit/tag/push，等待Planner审查。

## F0-02 账号系统（历史已验收，当前初始化见下方UAT说明）

先查看迁移状态再迁移；不得删除已有数据库或使用 fake。当前原 F0-01 SQLite（仅 contenttypes 已迁移）已验证可以正常升级。User 必须由 accounts/0001_initial 创建。

```powershell
Set-Location D:\Riichi\backend
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py createsuperuser
```

createsuperuser 交互输入自己的用户名和密码，自动创建选手档案；没有默认管理员凭据。UAT-FIX-01已关闭公开注册与普通账号登录；管理员访问/login，/players维护选手，/profile只维护管理员显示名称。选手昵称与内部技术用户名分别保存，界面不显示无意义内部用户名。旧自助注册行为只见历史报告。

浏览器统一使用同一个主机名（推荐 http://127.0.0.1:5173），不要混用 localhost 与 127.0.0.1。前端开发仍按上文启动 npm run dev，依赖更新后执行 npm ci。生产必须同源部署 API 反向代理并启用 HTTPS；Session Cookie HttpOnly/SameSite=Lax，写请求带 CSRF。CSRF_TRUSTED_ORIGINS 示例为两个明确的本地前端来源，生产来源应由环境明确配置。

登录状态由服务器 Session Cookie 恢复，密码、Session ID、认证 Token 均不写入 localStorage。公开注册不可用；内部选手没有可用密码与管理权限。管理员创建选手时仅接受昵称白名单。公网开放前仍需独立完成登录限流等加固。本次不提供密码找回、邮箱验证或第三方登录。

API 与请求示例、测试结果和限制见 [F0-02 交付报告](docs/project/F0-02-verification.md)。原 F0-01 报告和证据保留为历史快照。

## F0-03 麻将机资源管理（历史交付边界，已验收）

沿用上述虚拟环境、环境配置和启动命令，先检查并执行数据库迁移：

```powershell
Set-Location D:\Riichi\backend
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py migrate --noinput
```

管理员登录后打开 /machines，可新增、查询、编辑、切换可用/维护/停用状态并确认退役。普通账号不显示入口，直接访问页面或API也不获得权限。没有默认管理员账号；需要时交互执行createsuperuser。

最多4台非退役设备，维护和停用也占容量；数据库唯一槽位与CHECK约束兜底，退役释放容量。编号输入1～3位数字，保存为三位，不限001～004；现役编号唯一，退役后复用编号会建立新的物理实体ID。已退役资料只读，没有删除或恢复操作。available不代表赛事空闲，本阶段不调度设备。

API：GET/POST /api/v1/machines/，GET/PATCH /api/v1/machines/{id}/，POST /api/v1/machines/{id}/retire/。全部需要管理员Session，写请求必须携带CSRF；search按编号/名称搜索，status筛选，page分页。总览是未过滤的真实全局统计。

[本阶段报告、调用示例与验证边界](docs/project/F0-03-verification.md)。没有新增依赖，F0-01/F0-02证据保留；SQLite并发已实测，PostgreSQL实际连接/并发与公网部署仍未验证。

## F0-04 赛事领域基础（历史交付边界，已验收）

使用上方PowerShell启动命令，先showmigrations、migrate，再按需交互执行createsuperuser。管理员访问 `/tournaments`，创建/编辑草稿、搜索分页选择真实有效选手，检查规则和名单后明确确认启动。普通用户没有管理菜单或API权限。启动不分桌、不分配设备、不产生比赛成绩。

规则默认25000开局、30000返还、Uma [30,10,-10,-30]，轮数1～6；草稿允许名单未完整，启动需要4/8/12/16名有效选手。启动事务冻结规则和昵称快照，已启动只读，不支持删除或取消。

API（均需管理员Session，所有写请求带CSRF）：GET/POST `/api/v1/tournaments/`；GET/PATCH `/api/v1/tournaments/{id}/`；PUT `/api/v1/tournaments/{id}/participants/`；POST `/api/v1/tournaments/{id}/start/`。列表支持search/status/page。点数为整数、Uma用精确十进制字符串传递，oka只读。

F0-04当时的迁移、测试、HTTP/浏览器及数据库状态见 [原始交付报告](docs/project/F0-04-verification.md)，保留历史快照。当前本地迁移状态应由使用者通过showmigrations实查；当时D0-01未检查或修改数据库。PostgreSQL与公网部署仍未验证。

## F0-05 首轮分桌与物理设备（历史交付边界）

仍使用上方PowerShell命令：在backend执行showmigrations、migrate（无fake/重置），按需createsuperuser；启动Django及Vite后访问http://127.0.0.1:5173。管理员从已启动赛事详情进入“分桌工作台”(`/tournaments/{id}/rounds`)。

先在设备页登记真实可用设备，再确认生成第一轮。系统随机安排东南西北座次，按编号升序分配空闲available设备，资源不足整轮拒绝。刷新不重新随机，生成后无任意座次编辑。工作台可查看跨赛事占用，确认调整设备、释放或查看审计历史。

active占用的设备不能维护/停用/退役；先确认实体使用已结束并释放。释放不等于成绩确认或轮次结束，不支持重新开启已释放桌。F0-05当时第二轮及以上明确拒绝，等待未来已确认成绩与累计积分。

API：GET/POST `/api/v1/tournaments/{id}/rounds/`（生成体`{"round_number":1}`），GET `/api/v1/tournaments/{id}/rounds/1/`，GET `/api/v1/round-tables/{id}/`、`.../machine/history/`，POST `.../machine/reassign/`（`{"machine_id":3}`）、`.../machine/release/`（`{"reason":"实体使用结束"}`），GET `/api/v1/machine-resources/`。全部限管理员Session，写请求必须携带当前CSRF。

F0-05已正式验收，上述是F0-05当时行为；[原始交付报告](docs/project/F0-05-verification.md)保留当时QA与迁移记录。历史失败证据不修改；F0-06验证另行留档，不把历史结果冒称本轮通过。

## F0-06 完整个人赛工作流（候选）

管理员从赛事详情进入分桌工作台，完成：创建草稿/选择老板维护的有效选手→启动冻结→明确选择人数/4张真实物理桌并确认A～D→首轮随机→逐桌录入/保存草稿/正式确认→查看累计榜→生成下一轮→最后一轮公开抽签（如需）→二次确认正式完赛→查看唯一冠军及只读档案。换轮不重选或释放物理桌；故障换桌需原因和确认。

店内可以登记超过四张桌，单场最多四张。原始终局点数为整数，允许负数与零，范围±(2^53−1)；确认总和必须四倍赛事开局点数，异常只可存草稿。确认后锁定，未确认草稿不计分。积分以Fraction计算，分子/分母字符串无损保存，前端小数只作展示。TBD-001/002及OP-01～05均RESOLVED，详见统一规范。

旧F0-04已启动无分桌走新选桌流程；F0-05有效占用完整自动继承，released/异常需管理员复核。不重排首轮、不改旧ID或历史。无后续实体对局且全部配置轮次已存在，可复核为仅补历史成绩模式。新增迁移解除容量CHECK并建立桥接，旧单轮释放不能绕过赛事预留。见[兼容实现](docs/architecture.md#兼容与迁移已实现qa验证)。

迁移前先停旧服务写入、备份并在副本运行迁移/核验。**本轮未迁移Owner的backend/db.sqlite3**，只在独立QA库与副本验证；正式使用者须自行确认备份后按上文showmigrations/migrate正常升级。不得fake、删库或重置。

本轮独立QA复现示例（PowerShell，新的数据库名，仍需有效本地.env）：

```powershell
Set-Location D:\Riichi\backend
$env:DATABASE_URL = 'sqlite:///D:/Riichi/backend/.verification/my-f006-qa.sqlite3'
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test
# 管理员仅通过交互命令创建，不提供默认密码
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

前端仍运行npm run dev，访问http://127.0.0.1:5173，API前缀/api/v1。完整API契约、测试数量、文件SQLite并发/历史迁移及真实HTTP/UI证据见[F0-06报告](docs/project/F0-06-verification.md)。本次没有新增依赖或修改锁文件。PostgreSQL实连迁移/并发、HTTPS部署及公网安全仍UNVERIFIED，不等同已上线。F0-06之后仅集成测试、部署、安全加固、发布验收；不开发微信/团体赛，不拆新核心功能阶段。

## UAT-FIX-01：选手维护与 admin 初始化

当前整改说明、API和真实截图见[UAT-FIX-01报告](docs/project/UAT-FIX-01-verification.md)。本次没有新增迁移或依赖，原F0-01～F0-06报告/失败证据不改；不更改Owner数据库或指定密码。Git提交/推送/Tag由Owner执行，最终F0-06基线等待Planner复核与Owner再次人工验收。

管理员在选手管理新增昵称，即可用于4/8/12/16人赛事；内部唯一User使用不可用密码且无管理权限。状态可筛选有效/归档，归档不可加入新赛事。未被任何赛事引用的档案可以二次确认删除；已有草稿/历史引用时只能归档。物理删除只删除PlayerProfile，同时停用保留内部User，防止误删其他身份审计；不能通过User级联清除比赛历史。已启动赛事昵称、RoundSeat、成绩、榜单和冠军快照保持不变，旧草稿含归档/管理员档案需Owner手动调整名单。

以下命令必须由 **Owner在本地PowerShell交互执行**，密码不在聊天、参数、脚本、README或日志里传递。执行前确认目标库及备份、showmigrations；确需升级时先在副本核验再正常migrate，无fake/重置。

```powershell
Set-Location D:\Riichi\backend
# 默认开发库：新PowerShell窗口未设置DATABASE_URL时使用本地.env配置。
# 若当前窗口已有临时QA覆盖，先明确选择正确目标，勿将QA凭据当作admin密码。
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py init_admin
```

init_admin固定用户名为admin：不存在时委托Django createsuperuser交互创建；已存在且为有效staff/superuser时委托changepassword交互更新；已有普通/停用admin时直接拒绝，不自动提权或覆盖。创建冲突由Django拒绝，密码散列/强度校验沿用官方机制。没有启动自动重设或迁移改密。等价原生命令为`createsuperuser --username admin`和`changepassword admin`，须先人工核实账号归属与权限，不对未知普通账号提权。

**不同数据库独立初始化**：QA库在该窗口显式设置新的隔离DATABASE_URL后运行相同命令，其admin只存在于QA库；Owner开发库使用其.env中的实际配置；正式PostgreSQL在受保护的部署环境配置独立DATABASE_URL，再交互运行`manage.py init_admin --database default`（如配置多库，明确对应已配置alias）。命令只显示alias，不打印包含密码的数据库URL。不同库的账号/密码彼此独立，不读取旧credentials.json，不复用QA密码。

本轮没有为Owner实际设置或修改admin密码，需Owner运行上述命令输入指定密码。正式互联网部署使用独立高强度密码；已在聊天或文档公开的密码不适合作为长期生产密码。PostgreSQL实连、正式部署与公网安全仍UNVERIFIED。
