# F0-03 麻将机资源管理交付记录

日期：2026-11-03（Asia/Shanghai）。角色：Developer；状态：本地实现与自检完成，等待Planner验收。没有执行commit/tag/push。

## 基线与变更

- 开始时工作区干净，分支main，HEAD为`59be947ca133dbe18a63dcdc99e55a3243daed51`。
- 本地`baseline/F0-02^{commit}`解引用为同一Commit；F0-01与F0-02均按Owner任务登记为正式验收完成，Tag未修改。
- 新增backend/machines（实体、服务、序列化、API、迁移及测试）、前端machines服务/页面/编辑与退役组件及测试；更新路由、管理员入口、表单字段文案和文档。没有新增依赖，没有改造账号/选手认证。
- [完整变更文件](evidence/f0-03/changed-files.txt)、[Git状态](evidence/f0-03/git-status.txt)、[本阶段源码与文档SHA-256](evidence/f0-03/source-sha256.txt)。历史证据保持原状。

## 数据模型与状态

| 字段 | 含义 |
| --- | --- |
| id | 自增主键，稳定machineId，未来赛事引用此ID |
| machine_no | 三位ASCII数字业务编号；输入1～3位后zfill规范化，不限001～004 |
| name | 名称，必填，最多100字符 |
| location | 位置，可空，最多200字符 |
| description | 备注，可空，最多2000字符 |
| status | available、maintenance、disabled、retired枚举 |
| created_at / updated_at | 创建和最近修改时间 |
| capacity_slot | 内部容量字段，不在API中返回或接受 |

available/maintenance/disabled可以互相切换，均计入4台现役上限。只有available满足未来被分配的基本状态条件，但它不代表赛事空闲。

任意非退役状态可通过专用退役接口进入retired。退役释放槽位，保留ID、编号、名称、位置、备注及创建时间；更新时间记录退役。已退役设备只能查看，重复退役返回409，不能PATCH编辑或恢复。没有物理DELETE接口。

现役machine_no条件唯一。退役后可复用编号，但替代物理设备必须新建，获得新的id；历史记录继续指向原实体。未来Tournament以ForeignKey关联machineId，展示编号，并独立实现逻辑桌次、冲突检测和调度。本阶段没有Tournament、RoundTable、MachineAllocation或跨赛事占用锁。

## 容量与数据库约束

数据库为非退役设备要求一个非空1～4槽位，槽位唯一；退役设备必须为NULL。状态CHECK、槽位CHECK与唯一约束共同限定最多4台非退役设备，不能通过绕过序列化直接插入第五台。维护、停用也必须占槽。另有现役编号条件唯一、编号格式/纯数字及名称非空白CHECK。

创建按1～4尝试插入，每次失败的候选槽独立回滚，由数据库裁决唯一竞争，没有先count再insert的数量窗口。SQLite忙锁转换为409 machine_busy，提示刷新后重试；不会自动重放不确定HTTP写入。编辑/退役使用transaction.atomic、select_for_update及`WHERE status != retired`条件更新；条件更新同时保护SQLite中不支持行锁的情况。

实测分为：

- Django TransactionTestCase：SQLite共享内存数据库，8线程独立连接；成功计数与最终现役数一致，未超过4。
- 文件SQLite：独立QA数据库、8线程独立连接同步起跑，实测4次created、4次machine_capacity_full，最终4台。额外验证第五台拒绝、维护/停用计入容量、退役释放、相同编号新物理设备取得新ID。见[脚本](evidence/f0-03/sqlite-concurrency-check.py)和[日志](evidence/f0-03/sqlite-concurrency.log)。该次文件实测没有出现machine_busy。
- PostgreSQL实际迁移、实连与并发 **UNVERIFIED**。模型使用Django支持的约束设计，仍需正式环境单独验证。[Django约束参考](https://docs.djangoproject.com/en/5.2/ref/models/constraints/)。

## API 与调用示例

全部要求管理员Session；写操作执行既有CSRF检查。普通用户与匿名不能读写。成功`{"data":...}`，错误`{"error":{"code":"...","message":"...","fields":{}}}`，不回显数据库异常详情。

| 方法 / 路径 | 请求 / 结果 |
| --- | --- |
| GET /api/v1/machines/ | search按编号/名称搜索，status按枚举筛选，page分页（每页20） |
| POST /api/v1/machines/ | machine_no、name必填，location/description可空，status默认available |
| GET /api/v1/machines/{id}/ | 当前或历史设备完整公开台账字段 |
| PATCH /api/v1/machines/{id}/ | 修改现役设备资料/编号和非retired状态，拒绝空修改及未知字段 |
| POST /api/v1/machines/{id}/retire/ | 空JSON对象，保留历史并释放容量 |

列表data为count、next、previous、results、summary，默认machine_no/id排序。summary包含全库available/maintenance/disabled/retired计数及active和，不受列表过滤条件影响。

```json
{"machine_no":"8","name":"新登记设备","location":"场地位置","description":"设备备注","status":"available"}
```

上例POST后编号为008，返回稳定id；PATCH示例`{"status":"maintenance","location":"检修位置"}`；退役POST请求体`{}`。前端通过既有api服务获取当前CSRF Token并携带Cookie及X-CSRFToken，没有新增认证框架或在localStorage保存凭据。

重复编号409 duplicate_machine_no、容量满409 machine_capacity_full、忙锁409 machine_busy、重复退役409 already_retired、退役后编辑409 retired_readonly、非法字段/状态/编号400、非管理员403、DELETE/PUT405。内部capacity_slot与id不能由请求修改。

## 前端与实际浏览器

/machines替换为真实工作台；仪表盘和侧栏只给管理员展示设备入口。总览四项均来自API；加载/故障时统计置空，容量满禁用新建并给出说明，接口异常时不继续展示旧容量提示。

复用现有shadcn Sheet、Button、Card、Badge及Lucide图标。表单支持新建、编辑和只读详情；保存期间阻止重复提交及关闭，Esc可关闭未保存抽屉，关闭后在列表刷新完成后恢复焦点。退役提供取消及明确不可直接撤销确认。手机使用卡片式行布局，保留操作和时间，支持亮暗主题。

真实浏览器使用http://127.0.0.1:5173，经过Vite代理访问Django。服务运行在新建且被忽略的`.verification/f0-03-qa.sqlite3`，没有向开发数据库添加验证设备/账号。管理员通过createsuperuser --noinput创建，密码随机生成并仅保留在被忽略的本地QA文件，不写日志。

实际完成：匿名入口跳转登录；管理员空台账；非法编号反馈；POST创建008（id=6）；PATCH维护及另一台停用；容量满入口禁用；取消退役不执行写入；确认retire保留id=6；新增009（id=7）补足容量；退役详情只读无保存/恢复按钮；编号搜索、retired筛选、无匹配空状态；后端停止后的错误与恢复后重试；亮暗主题；390px和320px DOM宽度检查均无横向溢出；手机编辑抽屉与Esc关闭。普通用户实际注册/登录后无设备入口，直接/machines拒绝，直接真实GET设备API返回permission_denied。

截图与记录：

- [桌面暗色](evidence/f0-03/machines-desktop-dark.jpg)、[桌面亮色](evidence/f0-03/machines-desktop-light.jpg)
- [手机列表](evidence/f0-03/machines-mobile-dark.jpg)、[手机编辑](evidence/f0-03/machine-editor-mobile.jpg)
- [退役确认](evidence/f0-03/retirement-confirmation.jpg)、[网络错误](evidence/f0-03/network-error.jpg)
- [普通用户拒绝](evidence/f0-03/ordinary-user-denied.jpg)、[真实API拒绝](evidence/f0-03/ordinary-api-denied.txt)
- [最终DOM](evidence/f0-03/browser-machines-final-dom.txt)、[尺寸](evidence/f0-03/responsive-metrics.json)、[浏览器日志](evidence/f0-03/browser-logs.json)

浏览器验证时，沿用F0-02登录后进入仪表盘的既有行为，再经设备入口访问；一次等待目标页面超时、一次表单切换时输入目标失效，以及一次select标签定位未匹配，均在重新观察DOM后改为等待稳定页面/按combobox角色定位完成。没有因这些自动化定位问题修改账号模块。浏览器最终错误/警告为空。截图中的账号/设备均为独立QA库真实API数据，不是产品内置假数据。

## 迁移及实际工程命令

原开发SQLite先showmigrations并备份到被忽略的`.verification/f0-02-before-machines.sqlite3`。新增0001_initial与0002纯数字约束，正常migrate成功；第二项补充正则末尾换行边界，不修改已应用的0001或旧基线迁移。没有fake、重置、删库。

后端工作目录D:\Riichi\backend：

```powershell
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py makemigrations machines
.\.venv\Scripts\python.exe manage.py migrate --plan
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test machines -v 2
.\.venv\Scripts\python.exe manage.py test -v 2
.\.venv\Scripts\python.exe ../docs/project/evidence/f0-03/sqlite-concurrency-check.py
```

前端工作目录D:\Riichi\frontend：

```powershell
npm run format
npm run typecheck
npm test
npm run build
npm audit --json
```

联调后端用`DATABASE_URL=sqlite:///.verification/f0-03-qa.sqlite3`及`manage.py runserver 127.0.0.1:8000 --noreload`；前端npm run dev。最终服务已关闭。正常开发启动和管理员初始化见README。

| 项目 | 最终结果 / 证据 |
| --- | --- |
| Django check | PASS，0问题，backend-check.log |
| 迁移 | PASS，migrate.log、migrate-number-hardening.log |
| makemigrations检查 | PASS，No changes detected，migration-check.log |
| Django全量 | PASS，42/42（包含旧29项），backend-tests.log |
| 数据库约束 / 并发 | PASS，13项设备测试及额外文件SQLite测试 |
| TypeScript | PASS，生产构建中再次执行应用及工具配置检查 |
| Vitest全量 | PASS，4文件37/37（包含旧22项），frontend-tests-final.log |
| Vite构建 | PASS，CSS63.08kB、JS389.27kB，frontend-build-final.log |
| npm audit | PASS，0项漏洞，npm-audit.json；没有更改依赖或锁文件 |
| 真实HTTP | PASS，浏览器设备GET/POST/PATCH/retire真实请求，以及公开health200、匿名列表403 |

初次类型检查发现测试中未使用fireEvent导入，已删除；原始失败保留为typecheck-initial-unused-import.log。设备Vitest首次即全部通过。Node26/jsdom已有localStorage探测ExperimentalWarning仍出现，测试通过，没有启用Node凭据持久化。

## 自动审批限制与验证边界

一个组合式会话凭据处理+并发HTTP写入脚本在执行前被自动审批拒绝，返回原因仅为`blocked by policy`，无更具体说明，记录在http-script-policy-block.log。未执行该脚本，没有声称HTTP并发压测通过。改用限定QA文件数据库的ORM并发脚本，并通过浏览器完成真实认证API读写和状态流程；缺失/无效CSRF、管理员/普通/匿名权限矩阵由Django enforce_csrf_checks=True自动化测试覆盖。

PostgreSQL并发与实际部署、跨进程持续压力、真实手机硬件、网络不确定写入的完整故障注入均未验证。SQLite内存测试和文件8连接测试不是全规模负载测试。数据库终态历史策略由普通API执行，具备数据库管理权限者的手工SQL不在接口权限承诺内。未来赛事资源占用与冲突调度未实现。

## Git、安全与自检结论

所有F0-01、F0-02历史证据与迁移保留，未改账号/选手后端或认证请求服务。真实.env、QA凭据、数据库/备份、虚拟环境、依赖目录、缓存及构建产物均应被忽略；定向敏感信息/忽略检查见hygiene.log。没有硬编码生产密码或Token，没有全局CORS变更。

F0-03约定的本地功能和上述验证范围已完成，无已知阻断项。Developer自检不能替代Planner审查；停止本阶段开发，等待验收，Git由Owner手动执行。
