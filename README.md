# Riichi

Web 四人立直麻将赛事管理系统。V1.0 仅支持个人赛，当前任务 **F0-01** 建设可运行、可测试的工程骨架；赛事创建、注册登录、选手业务、分桌及计分均未实现。

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

选手注册、赛事领域对象、配置、分桌、计分和冠军判定属于后续 V1.0 任务。微信赛事发布、报名、绑定和播报仅为未来候选。

本地与 GitHub 基线当前均为“尚未建立”。F0-01 不执行 commit、tag 或 push；实现与验证完成后，等待 Planner 审查，由后续独立任务授权建立首次基线。
