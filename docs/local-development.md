# 本地启动与开发

本文从仓库根目录开始，所有路径相对仓库。启动器仅用于 Windows 本地开发/店内演示，不是生产部署方案。不要把 runserver 或 Vite 开发服务器开放到公网。

## Windows：日常使用

安装 Python 3.13（最低补丁版本见 `backend/.python-version`）、符合 `frontend/package.json` engines 的 Node.js / npm。当前为 Node.js ≥22.12、npm ≥10；Python 新版 3.14 不替代本项目的 3.13 环境。

双击 `start.bat`，按提示完成首次准备。启动器自身位置决定项目根目录，无需先切换终端目录，支持中文与空格路径；不要求管理员权限、不修改全局执行策略或安装全局依赖。

首次缺少环境/依赖时输入 `PREPARE`，将依赖安装到 `backend/.venv` 和 `frontend/node_modules`；后端使用 `requirements.txt` 精确版本，前端使用 `npm ci`。满足当前锁定依赖时跳过安装，锁文件变更或依赖不完整则重新提示。

无 `.env` 且没有外部 SECRET_KEY 时，输入 `CONFIGURE` 后从示例创建本地配置及随机密钥，不显示密钥、不覆盖原文件。环境变量仍优先于 `backend/.env`。启动器只接受现有 `config.settings.local`，不降低生产设置安全要求。

启动前只读检查系统与实际数据库迁移图。SQLite新文件在用户同意迁移前不会创建；已有SQLite以只读URI检查。需要迁移时展示数据库目标和待执行项，先自行备份/核对，再输入区分大小写的 `MIGRATE` 才执行原有迁移。不输入即停止；非交互模式不自动同意任何准备/迁移。PostgreSQL实连须在自己的安全环境另行验证。

服务绑定为后端 `http://127.0.0.1:8000`、前端 `http://127.0.0.1:5173`。后端health通过后才启动Vite，前端就绪后自动打开浏览器；启动进程内将API_PROXY_TARGET固定为本轮后端、VITE_API_BASE_URL固定为本轮前端同源地址，不改.env文件，防止旧跨域配置将登录请求送往其他服务。自定义部署配置请使用手动/正式部署流程。浏览器保持同一主机名，避免混用localhost与127.0.0.1。

启动窗口可以关闭，后台服务继续运行。退出时双击 `stop.bat`。重复启动复用已验证的现有服务并打开地址；端口属于其他程序时拒绝启动，不终止占用者。

### 管理员初始化

没有默认管理员密码。启动器发现没有有效管理员时只提示，不创建或重设密码。服务启动后另开终端，确认当前数据库与备份后运行：

```powershell
Set-Location backend
.\.venv\Scripts\python.exe manage.py init_admin
```

由 Owner 在本地交互输入密码。已有有效 `admin` 超级管理员走交互改密；普通/停用同名账号会拒绝覆盖或提权。开发、隔离QA和正式数据库彼此独立，不能把QA凭据当作管理员密码。

### 诊断及进程安全

日志保存在 `.runtime/launcher/<本次运行ID>/`：`backend.log`、`frontend.log`、worker输出。`state.json` 只保存本项目进程身份/阶段，不保存密码、Cookie或数据库URL；所有运行文件及安装缓存均由Git忽略。不要向他人发送含本地隐私的完整日志。

启动器以隐藏PowerShell进程持有Windows Job Object，应用以挂起状态创建、加入该Job后才运行，因此Node构建工具等子进程也受约束。停止前同时核对根目录、运行ID、命令行、PID、创建时间和可执行文件，并在同一内核句柄上重验与终止；不按进程名杀进程。进程已退出可清理过期状态；身份不符/状态损坏时拒绝终止，保留现场供人工核对。

若服务启动失败，本次创建的另一服务也会回收，日志保留；不会无提示重试、抢占端口或清理数据库。两次启动/停止之间用项目目录派生的命名Mutex互斥，不会启动多个实例。退出后只清理自己的进程状态，历史日志保留。

诊断时可直接运行（不会触发批处理末尾的关闭窗口等待）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -NoBrowser
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop.ps1
```

`-NonInteractive` 用于已准备环境的自动验证；遇到缺失依赖、配置或迁移会失败，不替代确认。可用进程级 `RIICHI_PYTHON` / `RIICHI_NODE` / `RIICHI_NPM` 指定现有工具路径，日常启动无需设置。Python优先复用现有虚拟环境，RIICHI_PYTHON只用于尚未创建虚拟环境时指定解释器；默认再查项目内运行时、Python Launcher和PATH。工具版本不符时不覆盖虚拟环境，需人工核对。

## Linux / macOS：手动运行

准备相同版本运行时后，在仓库根目录执行：

```bash
python3.13 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
backend/.venv/bin/python scripts/launcher_probe.py configure
cd backend
.venv/bin/python manage.py check
.venv/bin/python manage.py showmigrations
# 核对目标与备份后才执行
.venv/bin/python manage.py migrate
.venv/bin/python manage.py init_admin
.venv/bin/python manage.py runserver 127.0.0.1:8000 --noreload
```

`configure` 只在没有本地配置时使用；已有.env会拒绝覆盖。它从示例生成新的随机SECRET_KEY，不输出密钥。另开终端：

```bash
cd frontend
npm ci
npm run dev
```

没有为Linux/macOS提供进程启动器；手动Ctrl+C停止各服务。

## 开发与检查

数据库相关验证应使用独立QA库或备份副本，禁止删库、fake或改历史迁移来掩盖冲突。

```powershell
Set-Location backend
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test
```

```powershell
Set-Location frontend
npm run typecheck
npm test
npm run build
```

架构/规则见[架构](architecture.md)、[需求](requirements.md)、[完整赛事规范](F0-06-functional-spec.md)；实际启动器验证与未验证项见[本轮报告](project/windows-launcher-readme-verification.md)。
