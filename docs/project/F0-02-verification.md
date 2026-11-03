# F0-02 用户账号与选手档案交付记录

日期：2026-11-03，Asia/Shanghai。Developer 自检交付，待 Planner 外部验收。未执行 commit、tag、push，未开发赛事、设备实体、计分或微信功能。

## 基线、迁移与数据保护

- 工作目录 D:\Riichi，当前 main，HEAD 为 `94a1fec747806682602dd24f7edbbcc4e27d07f0`。
- `git rev-parse baseline/F0-01^{commit}` 同样为上述 Commit；附注 Tag 对象本身 SHA 不等于 Commit SHA，不代表冲突。
- 实施前 `showmigrations` 和数据库 introspection 确认：只有 django_content_type、django_migrations 两张表，已应用 contenttypes.0001_initial/0002_remove_content_type_name。一次手写 SQLite 查询命令因 PowerShell 引号转义出现 SyntaxError，没有修改数据；随后用 Django introspection 只读确认成功。
- 迁移前将 db.sqlite3 复制至被忽略的 backend/.verification/f0-01-before-accounts.sqlite3；原文件 SHA-256：`dc8ebab3f69f8899bbb2108e0ff5863e144c54b565457ee2091e7c99504f7b5d`。
- 生成 accounts/0001_initial（创建 AbstractUser 子类 User）、players/0001_initial（创建 PlayerProfile），先检查 migrate --plan，再正常 migrate。auth、accounts、players、sessions 迁移成功，没有删除数据库、fake 或改动旧迁移。
- PlayerProfile 的 user 为 OneToOne(settings.AUTH_USER_MODEL)，nickname 最大80字符，另存 created_at/updated_at。选手昵称与 username 独立。post_save 为新账号建立档案；注册在 transaction.atomic 中创建账号、档案并设置昵称，异常整体回滚。createsuperuser 也有对应档案。
- 开发数据库迁移后 User 数为0。所有 HTTP/浏览器验证账号在独立的 backend/.verification/f0-02-browser.sqlite3 副本中，未把测试账号灌入开发数据库。测试管理员通过 createsuperuser --noinput 创建，密码随机生成、不写日志，临时验证文件受 Git 忽略。

## API 契约

统一前缀 `/api/v1`。除原 health 契约外，成功为 `{"data": ...}`，失败为 `{"error":{"code":"...","message":"...","fields":{}}}`。校验错误400、CSRF/匿名/无权限403、方法错误405、注册并发冲突409。SessionAuthentication 的匿名拒绝为403，前端按错误 code 区分身份失效与权限不足。

| 方法与路径 | 访问条件 / 结果 |
| --- | --- |
| GET /auth/csrf/ | 匿名可用，设置 CSRF Cookie并返回 data.csrf_token，no-store |
| POST /auth/register/ | CSRF；username、nickname、password、password_confirm；201，成功后显式登录 |
| POST /auth/login/ | CSRF；username、password；Django authenticate/login 建立Session并轮换CSRF |
| POST /auth/logout/ | 已登录+CSRF，空对象；注销服务器Session |
| GET /auth/me/ | 已登录；id、username、is_staff、date_joined |
| GET /players/me/ | 已登录；本人档案 |
| PATCH /players/me/ | 已登录+CSRF；只允许 nickname |
| GET /players/?search=...&page=1 | 管理员；每页20项，按昵称/用户名搜索；count/next/previous/results |
| GET /health/ | 保持原匿名 liveness JSON，不表示数据库 readiness |

请求示例（浏览器客户端流程，示例输入不可作为默认账号）：

```javascript
const init = await fetch('/api/v1/auth/csrf/', { credentials: 'include' })
const { data } = await init.json()
await fetch('/api/v1/auth/register/', {
  method: 'POST', credentials: 'include',
  headers: { 'Content-Type': 'application/json', 'X-CSRFToken': data.csrf_token },
  body: JSON.stringify({ username: 'your_name', nickname: '你的昵称',
    password: '<your-strong-password>', password_confirm: '<same-password>' })
})
// login 请求体为 {username, password}；PATCH players/me 请求体为 {nickname}。
// 每次写前重新获取csrf初始化；登录会轮换CSRF，不能复用登录前Token。
```

档案和列表仅返回 id、username、nickname、date_joined、created_at、updated_at；没有密码散列、session、权限组、邮箱或敏感内部信息。注册拒绝 is_staff/is_superuser/is_active/groups/id 等未知字段，使用官方密码校验与散列。没有按他人ID修改档案的端点。

## 认证、CSRF 与前端

注册/登录/退出采用原生 Django JSON View，显式 csrf_protect；不使用 csrf_exempt。其余受保护API采用DRF SessionAuthentication及权限类。CSRF失败与API路由错误均返回JSON；CSRF响应不泄露内部拒绝原因。Session Cookie为HttpOnly、SameSite=Lax，生产Secure/HTTPS保持既有生产配置。开发通过同源Vite代理，可信来源仅明确的localhost:5173和127.0.0.1:5173，生产需显式设置。

前端 API 服务统一 credentials、CSRF初始化、错误和身份失效处理，不自动重试写请求。仅主题偏好存入localStorage；密码、Session ID、认证Token均不持久化。AuthProvider通过me恢复会话并隔离过期异步恢复结果。网络故障展示重试，与匿名状态分开。

公开页面 /login、/register；应用页面全部需要登录。/profile读取及修改本人昵称；/players额外需要管理员。顶部展示用户名、资料入口和退出；普通用户隐藏管理员菜单与入口。保持主题、仪表盘、面包屑、响应式导航；主要账号/业务正文13～16px，输入控件不小于46px。

## 实际命令与结果

后端（D:\Riichi\backend）：

```powershell
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py makemigrations accounts players
.\.venv\Scripts\python.exe manage.py migrate --plan
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test -v 2
```

结果：check零问题、原SQLite迁移成功、重复migrate无待应用项、makemigrations无变更、29/29测试通过（保留原F0-01全部15项）。涵盖注册/密码/重复用户名/敏感字段拒绝、事务回滚、唯一约束、会话恢复/注销/停用账号、匿名拒绝、普通/管理员权限、他人档案保护、CSRF缺失/无效/外站来源拒绝。

前端（D:\Riichi\frontend）：

```powershell
npm install --save-dev --save-exact @testing-library/react@latest @testing-library/user-event@latest jsdom@latest
npm run format
npm run typecheck
npm test
npm run build
npm audit --json
```

新增仅测试依赖并精确锁定：@testing-library/react 16.3.3、@testing-library/user-event 14.6.8、jsdom 30.1.3，用于真实DOM表单交互、路由守卫和会话恢复测试。后端没有新增第三方依赖。

最终结果：typecheck通过、3文件22/22测试通过（保留原health 8项）、Vite构建通过（CSS55.86kB、JS375.54kB）、audit零漏洞。新增测试涵盖注册校验/成功、API字段反馈、登录失败、会话恢复、网络重试、路由保护、个人修改、角色菜单、退出、Cookie与CSRF请求。

初次typecheck发现RTL getByRole不支持exact选项；第一次Vitest为21通过/1失败，原因是导航与面包屑同名。修复为限定主导航范围并使用精确正则后通过。失败输出保留于 frontend-tests-initial.log。Node26/jsdom探测localStorage产生ExperimentalWarning，不影响jsdom内表单/主题测试；没有启用Node持久存储或写认证凭据。

原始日志：[evidence/f0-02](evidence/f0-02/)。F0-01所有证据保持原状。

## 实际联调与浏览器检查

后端：设置 DATABASE_URL=sqlite:///.verification/f0-02-browser.sqlite3 后执行 `manage.py runserver 127.0.0.1:8000 --noreload`。前端 `npm run dev`，真实页面与代理地址 http://127.0.0.1:5173。

- 真实HTTP通过Vite代理验证health、CSRF缺失403、注册、登录、me、本人PATCH、普通用户列表403、退出会话失效、createsuperuser管理员列表搜索及返回字段白名单。见 http-integration.log；没有打印密码、Session Cookie或CSRF Token。
- 浏览器验证匿名/profile跳转/login；实际注册测试账号、登录、修改昵称、刷新后保留会话与新昵称、退出。
- 普通用户隐藏列表菜单，直接/players显示拒绝；管理员实际登录后可查询/搜索，搜索无结果显示空状态。
- 390px资料页及登录页实测 scrollWidth=390；桌面1440px检查登录/资料/列表；亮暗主题可切换，最终浏览器错误/警告为空。截图为隔离测试库中的验证账号，不是产品演示数据。
- 截图首次因视口调整尚未稳定出现截取区域不完整，随后等待视口稳定并重拍；尺寸以DOM读数确认，不将截图截取问题当作应用功能失败。
- 结束时关闭本任务的前后端验证服务；正常本地启动步骤见README，管理员须自行交互执行createsuperuser。

## Git、安全与限制

未执行commit/tag/push，未移动或删除F0-01基线。源码、迁移、测试、锁文件及文档为本次变更；开发环境、数据库副本、真实.env、QA管理员临时凭据、node_modules、缓存、dist均不入Git。定向敏感信息检查和git check-ignore检查结果见hygiene.log。完整变更清单见changed-files.txt，Git快照见git-status.txt。

已知限制：PostgreSQL实连、生产HTTPS/反向代理、真实手机硬件未验证；公网登录限流等安全加固未实现，必须独立完成后再公网发布。无找回密码、邮箱验证、微信或外部OAuth；无赛事、设备实体、历史战绩或计分。本次没有创建开发管理员账号或保留默认密码，管理员初始账号由Owner用createsuperuser创建。

自检结论：F0-02本地范围已实现并通过上述验证，无已知阻断项。Developer自检不替代Planner验收；停止开发，等待审查，不进入下一阶段。
