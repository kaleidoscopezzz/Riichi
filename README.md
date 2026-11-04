# Riichi

**轻量级四人立直麻将个人赛事管理系统**，帮助麻将馆管理员快速创建赛事、安排选手、录入成绩、重排座次并决出冠军；物理桌是辅助资源。

当前可运行正式基线为 **F0-05（CLOSED / PASS）**，已实现账号、选手、设备、赛事配置/启动、首轮随机及轮次级设备分配/释放。成绩、计分、后续轮次、冠军和赛事级固定选桌尚未实现。当前任务 **D0-01仅修订Markdown**；F0-06未启动，将在一个任务中完成V1.0全部剩余核心功能。

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

上述为复现命令，不代表每项已执行；以 [F0-01 实际验证报告](docs/project/F0-01-verification.md) 为准。生产构建输出到 `frontend/dist/`，开发服务器不能替代生产部署。

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
- [F0-06完整功能规范（目标，最终决策已落实）](docs/F0-06-functional-spec.md)

账号、选手、赛事配置/启动与首轮已实现。成绩、精确计分、累计榜、后续分桌、最终冠军/公开抽签和完赛自动释放统一纳入F0-06，不拆F0-07/F0-08。微信、团体赛仍为未来候选，不纳入V1.0。

当前正式基线 `baseline/F0-05`，Commit `41929da1e53f8bb481beb4ea3bc31b65f9ee86ff`，Branch main，Planner CLOSED / PASS；F0-01～05历史基线/报告均保留。D0-01不commit/tag/push；只有Planner批准文档、Owner推送文档Commit、远程内容核验一致后，才允许启动F0-06。

## F0-02 账号系统使用（已验收）

先查看迁移状态再迁移；不得删除已有数据库或使用 fake。当前原 F0-01 SQLite（仅 contenttypes 已迁移）已验证可以正常升级。User 必须由 accounts/0001_initial 创建。

```powershell
Set-Location D:\Riichi\backend
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py createsuperuser
```

createsuperuser 交互输入自己的用户名和密码，自动创建选手档案；没有默认管理员凭据。普通用户访问 /register，成功后到 /login 登录；/profile 修改本人昵称。只有管理员看到 /players 菜单并能搜索分页列表。昵称与用户名分别存储，当前只允许修改昵称。

浏览器统一使用同一个主机名（推荐 http://127.0.0.1:5173），不要混用 localhost 与 127.0.0.1。前端开发仍按上文启动 npm run dev，依赖更新后执行 npm ci。生产必须同源部署 API 反向代理并启用 HTTPS；Session Cookie HttpOnly/SameSite=Lax，写请求带 CSRF。CSRF_TRUSTED_ORIGINS 示例为两个明确的本地前端来源，生产来源应由环境明确配置。

登录状态由服务器 Session Cookie 恢复，密码、Session ID、认证 Token 均不写入 localStorage。注册/登录不会接受权限字段，普通用户没有管理员列表权限。公网开放前仍需独立完成登录限流等加固。本次不提供密码找回、邮箱验证或第三方登录。

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

F0-04当时的迁移、测试、HTTP/浏览器及数据库状态见 [原始交付报告](docs/project/F0-04-verification.md)，保留历史快照。当前本地迁移状态应由使用者通过showmigrations实查；D0-01未检查或修改数据库。PostgreSQL与公网部署仍未验证。

## F0-05 首轮分桌与物理设备

仍使用上方PowerShell命令：在backend执行showmigrations、migrate（无fake/重置），按需createsuperuser；启动Django及Vite后访问http://127.0.0.1:5173。管理员从已启动赛事详情进入“分桌工作台”(`/tournaments/{id}/rounds`)。

先在设备页登记真实可用设备，再确认生成第一轮。系统随机安排东南西北座次，按编号升序分配空闲available设备，资源不足整轮拒绝。刷新不重新随机，生成后无任意座次编辑。工作台可查看跨赛事占用，确认调整设备、释放或查看审计历史。

active占用的设备不能维护/停用/退役；先确认实体使用已结束并释放。释放不等于成绩确认或轮次结束，不支持重新开启已释放桌。第二轮及以上当前明确拒绝，等待未来已确认成绩与累计积分。

API：GET/POST `/api/v1/tournaments/{id}/rounds/`（生成体`{"round_number":1}`），GET `/api/v1/tournaments/{id}/rounds/1/`，GET `/api/v1/round-tables/{id}/`、`.../machine/history/`，POST `.../machine/reassign/`（`{"machine_id":3}`）、`.../machine/release/`（`{"reason":"实体使用结束"}`），GET `/api/v1/machine-resources/`。全部限管理员Session，写请求必须携带当前CSRF。

F0-05已正式验收，上述是当前代码行为；[原始交付报告](docs/project/F0-05-verification.md)保留当时QA与迁移记录。历史失败证据不修改，D0-01不重跑功能测试、不迁移或改依赖，也不把历史结果冒称本轮通过。

## D0-01与F0-06目标

F0-05当前仍最多4台非退役设备、轮次级MachineAllocation、仅首轮生成；尚未改成新目标。

F0-06目标为店内可登记5张或更多物理桌，单赛事首轮前显式选择1～4张并固定A～D映射，后续只重排选手/分组/四风，正式完赛自动释放。故障替换保留简化审计，不作为日常换轮步骤。新增迁移须安全解除capacity_slot容量依赖，保留machineId、旧分桌和设备历史，见[非破坏性兼容设计](docs/architecture.md#兼容与迁移设计建议尚未执行)。本任务没有执行这些改造。

TBD-001/002均为**RESOLVED**，已确认采用`split_rank_bonus_v1`与`performance_v1`。Planner五项最终决策已落实，详细规则、公开抽签、条件零和、完整流程及验收统一见[F0-06规范](docs/F0-06-functional-spec.md)：

- 终局点数允许负数/零，四人均为整数；正式确认总和必须4×开局，异常可存草稿但不能跳过校验。
- 后续分桌按累计分、第一/第二次数、逆序逐轮积分，完全相同按首轮持久化随机顺序；新轮四风重新随机。冠军全同仍公开抽签，不使用首轮兜底。
- F0-04已启动未分桌及F0-05已有分桌均须兼容；旧占用全部有效时继承固定桌位，已释放/异常需管理员复核。保留首轮与历史，新旧资源统一互斥。
- Fraction等精确有理数为权威计分与排名、无损存储；Decimal/字符串仅作精确输入解析，前端近似展示不排序，禁止浮点累计。允许修改冲突的旧测试断言，保留有效旧测试和全部历史验收证据，补齐新需求回归。

上述为F0-06目标，当前代码尚未实现；不做任意公式编辑器，不静默升级或重算历史。

F0-06是最后一次核心功能开发，须一次交付成绩到冠军完整闭环；之后仅集成测试、部署、安全加固及发布验收。D0-01完成后停止，等待Planner文档审查与Owner文档提交/远程核验。
