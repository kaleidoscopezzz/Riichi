# Riichi

Web 四人立直麻将赛事管理系统。V1.0 仅支持个人赛，当前 **F0-04** 提供账号、选手档案、设备资源和赛事领域基础。管理员可以创建赛事草稿、选择真实选手、配置规则并启动冻结；分桌、计分、冠军和设备占用调度尚未实现。

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

- [需求与 TBD](docs/requirements.md)
- [开发路线](docs/roadmap.md)
- [架构与目录](docs/architecture.md)
- [基线管理](docs/project/baselines.md)
- [开发约束](AGENTS.md)

账号注册、选手档案、设备和赛事配置/启动已实现；分桌、计分和冠军判定属于后续 V1.0 任务。微信赛事发布、报名、绑定和播报仅为未来候选。

当前正式基线 baseline/F0-03（0d7e96b0b920e490abbf7acd1d4aba38493025f9），Planner PASS。F0-01/F0-02历史基线保留；本次 F0-04 不执行 commit、tag 或 push，等待 Planner 验收和 Owner 手动 Git 操作。

## F0-02 账号系统使用

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

## F0-03 麻将机资源管理

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

## F0-04 赛事领域基础

使用上方PowerShell启动命令，先showmigrations、migrate，再按需交互执行createsuperuser。管理员访问 `/tournaments`，创建/编辑草稿、搜索分页选择真实有效选手，检查规则和名单后明确确认启动。普通用户没有管理菜单或API权限。启动不分桌、不分配设备、不产生比赛成绩。

规则默认25000开局、30000返还、Uma [30,10,-10,-30]，轮数1～6；草稿允许名单未完整，启动需要4/8/12/16名有效选手。启动事务冻结规则和昵称快照，已启动只读，不支持删除或取消。

API（均需管理员Session，所有写请求带CSRF）：GET/POST `/api/v1/tournaments/`；GET/PATCH `/api/v1/tournaments/{id}/`；PUT `/api/v1/tournaments/{id}/participants/`；POST `/api/v1/tournaments/{id}/start/`。列表支持search/status/page。点数为整数、Uma用精确十进制字符串传递，oka只读。

本阶段未增加依赖或改动锁文件。实际执行的迁移、测试、HTTP和浏览器检查、请求示例及工程限制见 [F0-04交付报告](docs/project/F0-04-verification.md)。全部旧证据保留。验证只迁移独立QA库；开发库尚未应用F0-04，正式本地使用前请正常执行migrate。PostgreSQL与公网部署仍未验证。
