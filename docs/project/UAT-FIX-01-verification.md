# UAT-FIX-01 整改与验证报告

日期：2026-11-04。状态：Developer 自检通过，未提交候选；等待 Owner 建立候选、Planner 独立复核及 Owner 再次人工点击验收。不得据此标记 F0-06 CLOSED 或建立 baseline/F0-06。

## 1. 范围、起点与数据保护

- 本地 `D:\Riichi`，`main`，起点及交付时 HEAD：`b9e83bb0c8e31ab660b37e7e0a46c1f0bb424e65`。GitHub 候选及 Planner 前轮审查结果来自 Owner 授权说明，本轮没有改远端或重新宣称远端核验。
- 只处理赛事列表对齐、老板维护选手、全站操作区一致性、安全 admin 初始化四项整改；不修改精确计分、排名、冠军及物理桌核心模型，不增加阶段或依赖。
- 无新增/修改迁移，无模型字段变更。既有 F0-01～F0-06 报告、测试证据及历史迁移保留；F0-05 仍 CLOSED / PASS。
- 所有新增用户、选手和赛事写入独立库 `backend/.verification/uat-fix-01/qa.sqlite3`；随机 QA 凭据只在忽略目录中使用，不读取旧 QA 凭据作为全局管理员来源。
- Owner `backend/db.sqlite3` 开始及结束 SHA256 均为 `C4738A1EADA032C19A2F9E33F2DCB555A961F1457321B5BD2EBCCD92FFA3A2C9`，没有执行 Owner 库迁移、清理、重置或密码修改。
- 收到的附件为本任务的文本要求；附件目录没有单独的 Word 文件。本报告依据其中四项已明确要求。

## 2. 四项整改结果

### 2.1 赛事列表

表头及数据行共享六列 Grid；名称左对齐，其余状态、人数、轮数、时间、操作容器及内容均居中。补充首列高优先级旧样式覆盖，长名称换行不挤压后五列；移动端保留卡片结构。

在真实 QA API 的四场赛事中包含草稿、已启动、完赛及长名称。1440px 最终截图及内容测量中，后五列中心与表头中心偏差均小于 0.01px。搜索、分页、筛选及窄屏同时复核。

- [修复前赛事列表](evidence/UAT-FIX-01/before-tournaments.png)
- [最终四行真实赛事截图](evidence/UAT-FIX-01/tournaments-four-rows-final.png)
- [最终内容中心测量](evidence/UAT-FIX-01/final-column-content-metrics.json)

### 2.2 雀庄老板维护选手

沿用 `User` + OneToOne `PlayerProfile`。管理员只提交昵称，服务在一个事务内生成唯一 `player_UUID` 技术用户名、不可用密码、非 staff/superuser 的内部 User 和选手档案。管理员自身档案不进入选手目录及新赛事名单，页面不展示内部用户名。

支持新增、分页、昵称搜索、详情、昵称修改、归档、恢复、无引用档案删除。状态沿用 `User.is_active`，有效名单同时排除管理员及归档选手。已被草稿或历史赛事引用时删除返回 409，只能归档。删除仅物理删除 PlayerProfile，并保留停用的身份行，避免通过 User 级联误删其他历史审计；不会恢复该档案 ID。

变更在 User → Profile 锁顺序下执行；SQLite 事务首句以 User 无值变更 UPDATE 取得写预留。创建异常原子回滚。既有已启动赛事的参赛 ID、昵称快照、座次、成绩、排名和冠军不重写。旧草稿若含归档或管理员档案，须管理员手动调整，不自动修复名单。

公开注册端点经 CSRF 检查后固定 403，不解析注册业务、不创建用户；`/register` 跳转登录且无注册入口。登录服务端拒绝非 staff，`me` 与后台 API 要求管理员；旧普通会话也不能访问。Session、密码散列、CSRF 和统一错误结构保留。

前端复用现有 Sheet/Button、统一请求和反馈，打开编辑/确认前重新取详情，提供成功提示及 400/403/404/409 错误；冲突后提示刷新核对，不自动重复写入。删除、归档、恢复均二次确认。

### 2.3 全站 UI 一致性

在明确操作区 `.machine-form-footer` 使用等宽 Grid，同时覆盖 shadcn `asChild` 链接和按钮，统一最小 44px 高度、内边距、圆角和间距；390px 及以下纵向堆叠。三个动作按可用宽度分配。成绩/抽签/完赛长按钮允许换行；图标按钮保留方形。统一搜索与筛选 46px 高度、分页触控高度及辅助文字，设备表格非名称列居中。

最终视觉检查另修复了新选手表单缺少 `account-form` 类的问题（输入框实测 50px 高），以及 `html min-width:320px` 在 Windows 垂直滚动条占位后引起的横向溢出。没有以全局隐藏 overflow 或全局按钮 width:100% 掩盖问题。

桌面详情关闭与进入工作台由修复前 62×44 / 130×36，变为各 314×44；390px 下各 330×44，纵向堆叠。前后截图来自基线前端只读快照与本轮前端，均访问独立 QA API。基线补拍为默认 1280px，整改桌面为 1440px，尺寸差异如实保留，不将不同视口冒称同一画布。

- [修复前完整按钮操作区](evidence/UAT-FIX-01/before-detail-footer-complete.png)
- [整改后桌面等宽按钮](evidence/UAT-FIX-01/after-detail-footer-final.png)
- [390px 详情操作区](evidence/UAT-FIX-01/detail-footer-390-dark-final.png)
- [320px 选手表单](evidence/UAT-FIX-01/player-editor-320-dark-final.png)
- [320px 赛事表单](evidence/UAT-FIX-01/tournament-editor-320-dark-final.png)
- [320px 麻将机表单](evidence/UAT-FIX-01/machine-editor-320-dark.png)
- [320px 成绩录入](evidence/UAT-FIX-01/result-320-dark.png)
- [390px 公开抽签](evidence/UAT-FIX-01/lottery-390-light.png)
- [390px 完赛确认](evidence/UAT-FIX-01/finish-390-light.png)
- [完赛后冠军与资源释放](evidence/UAT-FIX-01/ui-completed-390-light.png)
- [320px 登录及普通账号拒绝反馈](evidence/UAT-FIX-01/login-320-dark-final.png)
- [390px 浅色登录页](evidence/UAT-FIX-01/login-390-light-final.png)

### 2.4 安全 admin 初始化

新增 `manage.py init_admin [--database default]`。固定用户名 `admin`：不存在则委托 Django 官方交互 `createsuperuser`；已有有效 staff/superuser 则交互 `changepassword`；普通/停用同名账号直接拒绝，不提权、不覆盖。只接受已配置数据库 alias，显示 alias，不打印数据库 URL。密码不接受脚本参数/环境变量，不在启动或迁移时设置。

本轮只测试命令分支及官方交互委托，没有输入或设置 Owner 指定密码。Owner 在确认数据库和备份后于本地 PowerShell 执行：

```powershell
Set-Location D:\Riichi\backend
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py init_admin
```

开发库、QA 库、正式 PostgreSQL 独立选择 DATABASE_URL 后分别初始化，参见 [README](../../README.md#uat-fix-01选手维护与-admin-初始化)。正式公网使用独立高强度密码，曾公开的密码不宜作为长期生产密码。

## 3. API 契约与示例

所有路径以 `/api/v1` 开头；除匿名 health / CSRF 初始化外，后台要求有效管理员 Session。每个写请求携带 Cookie 与当前 `X-CSRFToken`；不能用前端隐藏入口代替服务端权限。成功为 `data`，错误为 `error.code/message/fields`，不返回密码散列、Session 或技术用户名。

| 方法/路径 | 输入与结果 |
| --- | --- |
| GET `/auth/csrf/` | 初始化当前 CSRF Token；前端只在内存请求内使用 |
| POST `/auth/register/` | CSRF 后固定 403 `registration_closed`，无注册能力 |
| POST `/auth/login/` | `{"username":"admin","password":"<由Owner本地输入>"}`；非 staff 为 403，错误/停用为 400 |
| GET `/auth/me/` / POST `/auth/logout/` | 管理员会话恢复 / `{}` 退出；写请求需 CSRF |
| GET `/players/?page=1&search=昵称&status=active` | 每页 20；status 可为空/active/archived；eligible=true 只返回有效普通选手 |
| POST `/players/` | `{"nickname":"选手甲"}`，201 返回选手档案 |
| GET / PATCH `/players/{id}/` | 详情 / `{"nickname":"新昵称"}`，200；字段严格白名单 |
| DELETE `/players/{id}/` | `{"confirmed":true}`，无引用则 200 `{"data":{"deleted":true}}`；引用则 409 |
| POST `/players/{id}/archive/` / `restore/` | `{"confirmed":true}`，状态已变化则 409 |
| GET / PATCH `/players/me/` | 仅管理员自身显示资料，保留原 API 兼容 |

选手对象包含 `id, nickname, is_active, reference_count, can_delete, created_at, updated_at`。缺失/非法字段 400，无权限 403，不存在 404，业务/并发冲突 409；health 原匿名契约不变。赛事 API 及精确积分契约不变，仅新名单校验排除管理员与归档档案。

## 4. 实际命令、环境及结果

环境：项目内 Python 3.13.18 / Django 5.2.18 / DRF 3.18.3，Node 26.3.0 / npm 11.16.0，SQLite QA。未全局安装，无依赖或锁文件变更。

后端命令在 backend 下以 `.\.venv\Scripts\python.exe` 执行，设置 `DATABASE_URL=sqlite:///D:/Riichi/backend/.verification/uat-fix-01/qa.sqlite3`。所有命令的完整输出在本轮独立证据目录：

| 命令 | 实际结果 / 证据 |
| --- | --- |
| `manage.py migrate --noinput` | PASS；新独立 QA 库正常应用既有迁移，[日志](evidence/UAT-FIX-01/migrate.txt) |
| `manage.py check` | PASS，0 issues，[最终日志](evidence/UAT-FIX-01/check-final.txt) |
| `manage.py makemigrations --check --dry-run` | PASS，No changes detected，[日志](evidence/UAT-FIX-01/migrations-check-final.txt) |
| `manage.py test` | PASS，108/108，[最终日志](evidence/UAT-FIX-01/backend-final.txt) |
| `python -m pip check` | PASS，[日志](evidence/UAT-FIX-01/pip-check.txt) |
| frontend `npm run typecheck` | PASS，[最终日志](evidence/UAT-FIX-01/typecheck-final.txt) |
| frontend `npm test` | PASS，8 files / 79 tests，[最终日志](evidence/UAT-FIX-01/vitest-final.txt) |
| frontend `npm run build` | PASS，2195 modules；JS 432.02KB / gzip133.66KB，[最后 CSS 修订后构建](evidence/UAT-FIX-01/build-layout-final.txt) |
| frontend `npm audit --json` | PASS，0 vulnerabilities，[最终 JSON](evidence/UAT-FIX-01/npm-audit-final.json) |
| `backend/.venv/Scripts/python.exe backend/verification/uat_fix_01.py` | PASS，229 次请求，[最终全尺寸 HTTP 回归](evidence/UAT-FIX-01/http-all-sizes.txt) |
| 浏览器真实操作与视觉检查 | PASS，[操作记录](evidence/UAT-FIX-01/browser-summary.txt)、[最终 36 组矩阵](evidence/UAT-FIX-01/browser-layout-matrix-final.json)、[控制台最终记录](evidence/UAT-FIX-01/browser-console-final.json) |
| Git、忽略、敏感信息、历史文件、文档链接、diff 检查 | 见[最终审计](evidence/UAT-FIX-01/final-audit.json)及[全部变更清单](UAT-FIX-01-files.md) |

前端最终测试后仅调整 html 的 CSS 最小宽度；该变化重新执行生产构建（内含 TypeScript）并完成 36 组浏览器边界回归。Vitest 在 Node 26 提示 `localStorage` 实验特性警告，全部测试通过；未为消除警告更改运行时或依赖。

真实联调使用后端 `runserver 127.0.0.1:8027 --noreload`（CSRF 允许隔离 5187/8027 来源），前端 `API_PROXY_TARGET=http://127.0.0.1:8027`、`npm run dev -- --host 127.0.0.1 --port 5187 --strictPort`。基线前端只读快照使用 5188。验证后退出 QA 会话、关闭自建页签、恢复浏览器视口并停止本轮三个服务，不影响 Owner 其他服务。常规本地启动仍见 README 的 8000 / 5173。

### 4.1 HTTP 与 UI 闭环

最终 HTTP 新建 16 名老板维护选手，覆盖昵称编辑、无引用删除、引用删除 409、归档与恢复、历史昵称快照不变、归档不能参赛、CSRF 缺失拒绝、普通账号禁止登录、公开注册关闭、退出后后台 403。实际新建并完成赛事：#12（4人1轮）、#13（8人3轮）、#14（12人2轮）、#15（16人6轮）；逐轮重排、整数成绩确认、Fraction 积分、必要公开抽签确认、唯一冠军及自动释放通过。

浏览器另直接新增/维护四名选手（#27/45/46/47），无需本人注册，创建 #8 四人一轮赛事，选择真实 QA 物理桌005、故障替换006并填写原因；四人25000确认，同分公开抽签完整顺序录入后单独确认，正常完赛，冠军为“UI维护选手四”，资源释放，刷新保持。实际执行编辑、归档、恢复；UI 物理删除仅打开确认后取消，真正删除由 HTTP 与自动测试验证，不冒称浏览器完成删除。

1440/390/320、深浅主题下检查仪表盘/选手/设备/赛事/个人资料/设置共 36 组，最终均 `scrollWidth <= documentElement.clientWidth`；另检查登录、赛事创建/详情、分桌工作台、成绩录入、故障替换、公开抽签、完赛确认。像素检查与测量互补，DOM 测试不能替代截图。

### 4.2 测试调整与失败记录

- 原账号测试 14 项改为 15 项：自助注册正向断言被关闭注册不创建账号替代，原密码校验/散列、事务一致、唯一档案、Session/CSRF 等有效验证保留，并补管理员初始化安全分支。新增选手测试 10 项。
- 赛事旧断言中“管理员自身档案可参赛”改为拒绝，并用四名普通选手保留名单编辑正向回归；人数断言排除管理员。昵称选择器断言改用昵称与稳定档案 ID，替代技术用户名。
- 前端旧自助注册流程改为 `/register` 无表单且不请求注册，普通用户仪表盘改为权限拒绝。新增选手页面 9 项测试覆盖 CRUD、确认、错误及无自动写重试；原有效赛事/成绩/设备等测试继续运行。
- 早期后端旧注册解析/管理员名单断言失败保留于 backend-initial/second/complete.txt。注册视图最终直接关闭，避免先解析任意注册负载。最终 108 项通过。
- 早期前端旧菜单/显示文案断言失败保留于 frontend-initial/second.txt。frontend-complete.txt 另记录默认 Vitest glob 意外发现忽略目录中的基线快照、重复运行旧测试（152 项中 9 项失败）；现显式仅发现 `src/**/*.{test,spec}.{ts,tsx}`，没有删除任何维护中的测试，最终 79 项通过。
- 开始时 QA 种子脚本相对凭据路径写错，数据已进入独立库；随后在正确忽略路径重新生成本轮随机 QA 凭据，没有重置数据库。浏览器少数动画期元素定位失败/HMR 关闭表单，均重新读取状态再操作，未盲目重放写请求。
- 原始截图保留；部分早期截图包含动画中间帧，正式对比使用本报告链接的 complete/final 图，不用原始中间帧冒充最终效果。
- 最终文件审计首轮仅发现 players/views.py 文件末尾多余空行，diff --check 返回 2；已修正，首轮 audit-initial.json / diff-check-initial.txt 保留，最终重新审计。

## 5. 安全、变更与交付边界

新增接口管理员权限、严格字段、CSRF 缺失/无效、确认与冲突均有测试；新选手密码不可用且无管理员权限。日志与截图不含 Owner 密码、Session Cookie 或 CSRF Token，QA 凭据未进入版本化文件。没有新增 csrf_exempt、全局 CORS、认证 Token 持久化、密码启动覆盖或破坏性迁移。

全部新增/修改文件及逐文件状态见[清单](UAT-FIX-01-files.md)，证据与源码分列；Git 暂存为空、无删除、无 commit/tag/push，main/HEAD 不变。未修改历史迁移、锁文件或既有验收证据。工作区保留本轮未提交修改，供 Owner 审查后提交。

## 6. 未验证项与自检结论

- **UNVERIFIED**：Owner 本地指定 admin 密码的实际交互输入与登录，需 Owner 执行，不属于自动化设置完成。
- **UNVERIFIED**：PostgreSQL 实连迁移/并发、正式部署、HTTPS/公网登录限流及真实生产环境；沿用原阶段限制。
- 浏览器删除确认后取消；HTTP 实际删除已通过。QA 抽签为隔离环境人工模拟签条记录，不冒称真实赛事抽签。
- Owner 仍需再次人工点击验收；本报告不能替代 Planner 独立源码审查或双端基线核验。

Developer 自检：授权四项整改完成，自动化、真实 HTTP、浏览器与文件审计通过，无已知阻塞实现问题。交付未提交候选后停止，不进入下一阶段。

## 7. Owner 追加：全站下拉组件统一整改

2026-11-04，Owner 在未封版 UAT-FIX-01 追加 UI 问题。本节是原候选的增量记录，前六节的实际命令、截图、失败及通过证据全部保留；没有新建核心开发阶段。本项不修改任何版本化后端文件、数据库模型、计分/赛事服务或 API 契约。

### 7.1 全量清单与统一实现

对整个 `frontend/src/` 检索 `<select>` / `<option>`，原有7个业务文件、9处下拉，已全部迁移，详见[实际使用位置清单](UAT-FIX-01-select-inventory.md)。赛事/设备/选手筛选、设备状态、总轮数、查看轮次、首轮选桌/旧兼容复核、故障替换目标、公开抽签顺位均纳入。

新增唯一 `frontend/src/components/ui/select.tsx`，复用已锁定的 `radix-ui` Select，无新增依赖。业务只提供数据/选中值/回调，不维护页面私有菜单。通过Portal将菜单置于裁剪容器之外、Popper碰撞避让、z-index80高于现有Sheet；深浅主题共用原颜色变量，46px触发器、至少44px选项、圆角/边框/图标/焦点统一，选中项金色标记、悬停/禁用、阴影及滚动指示一致。

长选项完整换行，菜单最大360px、滚动区最大310px；窄高视口通过flex/min-height:0继续收缩，不越界。Popper采用updatePositionStrategy=always在展开期间跟随Sheet动画；取消全局平滑滚动，确保快速键盘焦点滚动立即定位。沿用Radix方向键、Enter、Escape、Home/End、焦点及ARIA。所有触发器显式标签，空值和数字ID在边界转换后保持原API参数，表单验证和禁用条件保留，忙碌时不再修改选择。

业务源码最终原生标签匹配为0；真实浏览器也未发现可交互原生select。Radix内部不可交互的 `aria-hidden` 隐藏表单桥接保留，负责required/FormData语义；它不提供操作系统菜单，通用测试专门覆盖这点。

### 7.2 本次实际验证

新证据均写入 `evidence/UAT-FIX-01/select/`，不覆盖本轮前半段或F0-01～F0-06的证据。

| 验证 | 实际结果及证据 |
| --- | --- |
| `npm run typecheck` | PASS，[日志](evidence/UAT-FIX-01/select/typecheck-final.txt)；最后样式调整后的build再次内含typecheck |
| `npm test` | PASS，9 files / **86 tests**，[最终定位修订后日志](evidence/UAT-FIX-01/select/vitest-position-final.txt) |
| `npm run build` | PASS，[最终构建](evidence/UAT-FIX-01/select/build-position-final.txt)，内含typecheck；JS487.44KB/gzip151.82KB |
| `npm audit --json` | PASS，0漏洞，[JSON](evidence/UAT-FIX-01/select/npm-audit.json) |
| QA环境 `manage.py check` | PASS，0 issues，[日志](evidence/UAT-FIX-01/select/backend-check.txt) |
| QA环境 `manage.py test` | PASS，**108/108**，[日志](evidence/UAT-FIX-01/select/backend-tests.txt)；后端版本化代码无本项增量 |
| 全站布局 | PASS，1440/390/320 × 深浅主题 × 6页面 = **36组**，无横向溢出，[矩阵](evidence/UAT-FIX-01/select/layout-matrix-final.json) |
| 展开菜单 | PASS，3个目录筛选 × 3宽度 × 2主题 = **18组最终展开检查**，均在视口内且无选项横向溢出，[测量](evidence/UAT-FIX-01/select/expanded-menu-metrics-final.json) |
| 快速键盘/定位复查 | PASS，九类下拉 × 3宽度 × 2主题 = **54组**，全部在视口内，[最终矩阵](evidence/UAT-FIX-01/select/runtime-regression-settled.json)；最终两项定位修订后无新增ResizeObserver通知，[运行日志](evidence/UAT-FIX-01/select/vite-runtime-diagnostic.txt) |
| 关键Sheet/工作台 | PASS，选桌、设备状态、赛事轮数、抽签、故障替换、查看轮次逐项展开，长昵称/17选项滚动、重复选手禁用、清空选桌禁止预览、真实Tab/Enter/Escape恢复焦点，[记录](evidence/UAT-FIX-01/select/browser-summary.txt) |
| 扫描/Git/凭据/Owner库 | [最终增量审计](evidence/UAT-FIX-01/select/audit.json)、[文件清单](UAT-FIX-01-files.md) |

新增通用组件7项交互测试：真实Portal鼠标选择/焦点、方向键跳过禁用项/Enter/Escape、空值回传、受控更新与ARIA/禁用、表单值及required、长选项与大量动态项、Sheet嵌套Escape层级。既有业务测试改用实际combobox/option交互，保留原API参数断言，不将通用组件mock为原生select。jsdom缺少布局/指针捕获的兼容只在测试setup中使用，几何、避让、滚动与视觉由真实浏览器验证。

沿用独立QA服务8027/前端5187及随机QA凭据，没有使用Owner密码。本项通过真实API为浏览器准备 #16待选桌赛事与 #17十六人全同分待抽签赛事，含长昵称，以验证真实动态选项；浏览器没有提交新分桌、故障替换或抽签记录，仅检查选项/本地表单并取消。已完成的六轮赛事 #15 从第六轮切换第二轮查看，成绩保持只读。上文229次完整HTTP闭环是前次整改证据，本项未重复宣称重新执行该脚本。

### 7.3 真实展开截图

- [桌面深色赛事筛选及选中标记（最后修订）](evidence/UAT-FIX-01/select/tournament-filter-1440-dark-position-final.png) / [桌面浅色](evidence/UAT-FIX-01/select/final-tournaments-1440-light.png)
- [390px深色设备筛选](evidence/UAT-FIX-01/select/final-machines-390-dark.png) / [320px浅色真实Tab导航](evidence/UAT-FIX-01/select/keyboard-tab-320-light-final.png)
- [选手筛选390px浅色](evidence/UAT-FIX-01/select/final-players-390-light.png)
- [设备编辑390px浅色](evidence/UAT-FIX-01/select/machine-edit-390-light.png)
- [总轮数320px深色](evidence/UAT-FIX-01/select/round-count-320-dark.png) / [桌面浅色](evidence/UAT-FIX-01/select/round-count-1440-light.png)
- [选桌390px深色](evidence/UAT-FIX-01/select/table-picker-390-dark.png) / [浅色](evidence/UAT-FIX-01/select/table-picker-390-light.png)
- [故障替换桌面浅色](evidence/UAT-FIX-01/select/replacement-1440-light.png)
- [抽签长选项320px深色](evidence/UAT-FIX-01/select/lottery-320-dark-final.png) / [浅色（最后修订）](evidence/UAT-FIX-01/select/lottery-320-light-position-final.png) / [End滚动到末项](evidence/UAT-FIX-01/select/lottery-end-320-dark-final.png)
- [六轮查看桌面浅色](evidence/UAT-FIX-01/select/round-view-six-1440-light.png) / [600px高视口收缩、选中末项仍可见](evidence/UAT-FIX-01/select/round-view-collision-1440x600-dark-final.png)

截图包含应用上下文和实际展开项，未用收起状态或DOM测试替代像素核查。

### 7.4 诊断记录、限制与停止

首次typecheck发现测试工具把Playwright的exact参数误用于Testing Library，已修正，保留typecheck-initial.txt。首轮86项Vitest即通过；Node26 localStorage实验性警告仍如实保留，无新增测试依赖。

浏览器窄高视口曾发现动态available-height约束使第六轮选中项被遮住，统一滚动区改为min-height:0及固定上限，让Radix flex收缩/滚动正常工作；最终截图显示第六轮可见。自动矩阵最初直接聚焦屏幕外触发器产生4条越界测量；实际点击后的18组均通过，但后续快速Tab/Enter复查仍复现滚动竞争，不能只当作测试工具问题。定位到html全局smooth滚动使焦点尚未滚到位就开启菜单，改为auto后，九类入口54组快速键盘回归全部通过。Sheet动画期间使用Popper持续跟随，保持菜单附着。原始54组文件和截图均保留，最终以runtime-regression-settled.json为准。动画/滚动中点击定位失败后先重读状态再用键盘打开，没有重复业务提交。

另在停止首个开发服务时观察到ResizeObserver运行时通知；console-only记录不能替代window error诊断。因此重新启动服务保存完整Vite日志，修订前记录2条；启用持续定位后两轮54组复查无新增此通知。没有屏蔽error、修改全局ResizeObserver或patch依赖。排查参考[Radix官方Select文档](https://www.radix-ui.com/primitives/docs/components/select)及[上游相关定位/ResizeObserver问题](https://github.com/floating-ui/floating-ui/issues/3512)，并未仅凭相似上游报告认定根因；本地快速键盘、动画和日志复查为本报告的实际证据。

本项没有新增迁移/依赖、改Owner库或执行commit/push/tag；QA会话、页签、视口及服务结束后清理。Owner admin交互密码、PostgreSQL实连、生产环境与真实手机硬件仍未验证；本次手机指浏览器320/390px视口检查。Developer自检通过后等待Owner再次点击及Planner复核，当前候选仍未封版。
