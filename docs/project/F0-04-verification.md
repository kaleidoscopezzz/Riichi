# F0-04 Tournament 赛事领域基础交付与自检

日期：2026-11-03（Asia/Shanghai）。Developer 自检：PASS；等待 Planner 源码审查，不替代外部验收。没有执行 commit、tag、push，没有进入下一阶段。

## 1. 基线与工程文件

开始时工作区干净，分支 main，HEAD及本地baseline/F0-03解引用均为 `0d7e96b0b920e490abbf7acd1d4aba38493025f9`。Owner确认F0-03 Planner PASS；F0-01/F0-02/F0-03标签保留不动。未执行本次GitHub远程引用核验，不宣称已建立F0-04双基线。

主要新增：

- `backend/tournaments/`：apps、models、rules、serializers、services、views、urls、tests、0001_initial迁移及包初始化文件。
- `frontend/src/services/tournaments.ts`：契约、API、精确Oka预览。
- `frontend/src/pages/tournaments.tsx`、`tournaments.test.tsx`：赛事工作台与行为测试。
- `frontend/src/components/tournament-editor.tsx`：分区表单、分页选手选择器、详情、启动确认。
- 本报告和 [F0-04证据目录](evidence/f0-04/)：实际日志、隔离QA复现脚本、截图、Git清单。

修改：backend配置注册App/URL；players/views.py增加可选eligible筛选且保持默认查询和响应字段；前端路由、角色菜单、仪表盘入口与当前阶段文案、统一错误字段标签、管理守卫通用文案、样式；AGENTS、README、requirements、architecture、roadmap、baselines。没有新增依赖、修改锁文件、历史迁移、账号认证实现、设备实现或旧阶段证据。

本次共98个变更文件：16个已跟踪文件修改、82个新增文件（包含完整过程证据）。完整逐文件清单见 [changed-files.txt](evidence/f0-04/changed-files.txt)，Git状态见 [git-status.txt](evidence/f0-04/git-status.txt)，源码SHA256见 [source-sha256.txt](evidence/f0-04/source-sha256.txt)。不把本地运行资源计入交付文件。

## 2. 领域模型与关系

Tournament包含稳定id、名称(120)、说明(3000可空)、轮数、开局点数、返还原点、四项Uma、draft/started、创建者FK User(PROTECT)、创建/更新时间、可空启动时间，以及不对外暴露的revision。

TournamentParticipant包含id、Tournament FK(PROTECT)、PlayerProfile FK(PROTECT)、昵称快照和创建时间；数据库UNIQUE(tournament,player)防重复。User与PlayerProfile仍使用原有一对一身份边界，无第二套账号。有效管理员有选手档案时也允许参赛。

数据库CHECK约束：轮数1～6、点数正数及存储上限、名称非空白、draft必须无started_at/started必须有started_at。名单人数、有效账号及Uma内容由服务/API校验；不宣称跨行规则已全部由CHECK覆盖。没有Round、RoundTable、MachineAllocation或赛事设备关联表。

## 3. 精确配置和Oka

默认开局25000，返还30000，Uma ["30","10","-10","-30"]。点数为JSON整数，1～2147483647；拒绝布尔、JSON小数及数字字符串。Uma恰好四项，顺序对应名次，接受整数或普通十进制字符串，保存十进制字符串；拒绝浮点JSON、NaN/Infinity/科学计数法，单项最多64字符。

Oka由`rules.derive_oka`使用Decimal计算`4*(return_points-starting_points)/1000`，API以字符串返回，不能独立填写。默认"20"，25001/30000为"19.996"。前端用BigInt千分位预览，保存后以后端结果为准。不做半庄得分、累计排名或冠军计算。

点数整数存储范围和Uma字符上限为工程边界，不作为已批准赛制限制；没有自行增加Uma总和、递减顺序、点数千分倍数或奖励规则。更具体精度/数值规则待Planner确认。TBD-001（半庄同点顺位）和TBD-002（累计同分冠军决胜）保留，不阻止创建/启动。

## 4. 名单与冻结事务

草稿允许0～16人；创建/PATCH支持participant_ids，PUT专门替换名单。拒绝重复、不存在或账号停用的选手。启动时重新校验全部配置和4/8/12/16人，保存各选手当时昵称快照，写started及started_at，一次事务提交。

所有公开修改入口共用`mutate_tournament`：事务第一条数据库语句是对`status=draft`父行的条件UPDATE(revision+1)，在读取名单之前争取同一写锁。SQLite串行写者；PostgreSQL由UPDATE取得行锁。名单替换、规则编辑与启动不走分离的无锁路径。SQLite锁忙返回409 tournament_busy，前端不自动重放写操作。[Django官方说明SQLite的select_for_update无效](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update)；本实现不依赖该锁保护SQLite赛事父行。

启动后全部写入口拒绝，重复启动already_started。昵称后来修改不影响启动快照；数据库管理员直接SQL写入不属于普通API冻结保证。没有乐观版本表单冲突提示：两个合法草稿编辑按照事务顺序提交，后提交者覆盖所提交字段；启动与编辑竞态受父行写锁保护。

测试故意在昵称快照bulk_update已经执行后、赛事状态save前抛出数据库异常，验证快照、状态、时间和revision全部回滚。创建/PATCH中名单失败也回滚配置，无部分保存。

## 5. API及请求示例

全部需要管理员Session，写请求先GET `/api/v1/auth/csrf/`，将返回的当前token放X-CSRFToken并携带会话Cookie；沿用既有API层，不记录凭据。

| 方法与完整路径 | 说明 |
| --- | --- |
| GET `/api/v1/tournaments/` | 每页20，按created_at/id降序，search名称、status=draft或started、page分页 |
| POST `/api/v1/tournaments/` | 创建草稿，name/round_count必填，其余配置默认，可同时原子选择participant_ids；201 |
| GET `/api/v1/tournaments/{id}/` | 配置、Oka、状态/时间、人数、名单、预计每轮桌数；200 |
| PATCH `/api/v1/tournaments/{id}/` | 原子编辑草稿配置和可选participant_ids；200 |
| PUT `/api/v1/tournaments/{id}/participants/` | 替换完整草稿名单；200 |
| POST `/api/v1/tournaments/{id}/start/` | 空对象，校验后冻结；200 |
| GET `/api/v1/players/?eligible=true&search=昵称&page=2` | 复用原管理员选手API，筛选有效账号，仍正确分页；默认接口行为/字段不变 |

创建示例（数字ID必须替换为自己真实API查询所得的档案ID，不能把示例当成已注册选手）：

```json
{"name":"个人赛草稿","description":"","round_count":3,"starting_points":25000,"return_points":30000,"uma":["30","10","-10","-30"],"participant_ids":[]}
```

名单替换：`{"participant_ids":[1,2,3,4]}`；原子编辑：`{"name":"更新名称","round_count":6,"participant_ids":[1,2,3,4]}`；启动：`{}`。

成功统一为`{"data":...}`，列表data含count/next/previous/results；详情含participant_count、participants、expected_table_count。合法人数桌数为人数/4，不完整草稿返回null。名单元素含player_id、display_name、username、is_active和display_name_snapshot；started展示快照，draft展示当前昵称。创建者只返回用户ID，没有密码、Session或内部revision。

错误统一为`{"error":{"code":"...","message":"...","fields":{...}}}`：输入400（字段错误），匿名/普通用户403，CSRF403，不存在404，冻结/重复启动/忙锁409，不支持方法405。拒绝status/created_by/started_at/revision/oka及未知字段。没有DELETE、取消、恢复或完赛API。

## 6. 页面与视觉

管理员 `/tournaments` 替换占位：真实列表、名称搜索、状态筛选、分页、加载、空结果与失败重试；分区表单展示基础信息、规则、选手选择和摘要，精确显示Oka。选手支持真实搜索与跨页选择、已选标签、去重、16人上限。草稿保存只保存草稿。

详情展示全部规则、名单、时间和预计每轮桌数；启动前重新GET详情并要求独立确认，提示不可修改且不会分桌。非法人数/停用账号不允许前端启动，后端仍再次验证；已启动没有编辑入口。按钮忙态禁止重复写入，Sheet提供焦点/键盘访问及关闭操作。

沿用Riichi Premium海军蓝/石墨色/金色、现有shadcn Sheet/Button/Badge，兼容亮色与手机。普通用户导航、仪表盘隐藏赛事入口，直接URL被守卫拒绝；服务端也拒绝所有管理接口。界面没有假赛事、假成绩或演示统计。

截图均来自**独立QA库**，画面中的验证赛事/账号不是正式或演示生产数据：

- [最终深色赛事列表](evidence/f0-04/tournaments-desktop-dark-final.png)、[亮色列表](evidence/f0-04/tournaments-desktop-light.png)
- [最终启动只读详情](evidence/f0-04/started-detail-dark-settled.png)、[启动确认](evidence/f0-04/start-confirmation-dark.png)
- [390px深色表单](evidence/f0-04/editor-mobile-dark-final.png)、[390px亮色表单](evidence/f0-04/editor-mobile-light-final.png)、[320px列表](evidence/f0-04/tournaments-mobile-light.png)

早期未带final/settled的截图有Sheet入场动画中间帧或临时视口变化，保留过程证据，移动端验收以前述final截图与最终几何记录为准。

## 7. 迁移和本地启动

先读取原迁移图，[migrations-before.log](evidence/f0-04/migrations-before.log)显示F0-03全部已应用。0001仅新增赛事两表及约束，依赖players/0001与自定义User。无删除数据库、fake、重置或修改旧迁移。

验证使用SQLite backup从开发库复制到被忽略的`backend/.verification/f0-04-qa.sqlite3`，在副本正常migrate并由官方createsuperuser初始化QA管理员；其他验证选手也只在副本。开发库原User/Profile/Machine均0行，前后SHA256不变；本次没有把F0-04迁移写入开发库。

实际运行：QA Django `127.0.0.1:8000 --noreload`、Vite `127.0.0.1:5173`。验证结束关闭QA服务与临时浏览器，保留忽略的QA库/凭据供本机复核。

正式本地使用（两个PowerShell窗口）：

```powershell
Set-Location D:\Riichi\backend
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

```powershell
Set-Location D:\Riichi\frontend
npm ci
npm run dev -- --host 127.0.0.1
```

已有管理员无需重复创建。环境密钥初始化依README，不能使用QA凭据作为默认密码。访问`http://127.0.0.1:5173/tournaments`；API根`http://127.0.0.1:8000/api/v1/`。

## 8. 实际自动化结果

环境：Windows PowerShell，Python3.13.18、Django5.2.18、Node26.3.0、npm11.16.0。依赖锁不变，无全局安装。

| 实际命令 | 结果 / 证据 |
| --- | --- |
| `.venv/Scripts/python.exe manage.py check` | PASS，0问题；backend-check-final.log |
| `manage.py migrate --noinput`（DATABASE_URL指向独立QA库） | PASS，首次应用tournaments/0001；qa-setup.log；再次无待执行迁移migrate-final.log |
| `manage.py makemigrations --check --dry-run` | PASS，No changes detected；migration-check-final.log |
| `manage.py test -v 2` | PASS **56/56**，含旧42和新增14；backend-tests-delivery.log |
| `npm run typecheck` | PASS；typecheck-delivery.log |
| `npm test` | PASS **49/49**，5文件，含旧37和新增12；frontend-tests-delivery.log |
| `npm run build` | PASS，含应用和Vite配置TS检查；frontend-build-delivery.log |
| `npm audit --json` | PASS，0漏洞；npm-audit.json |
| 项目venv运行`sqlite-concurrency-check.py` | PASS，6组真实文件SQLite竞态；sqlite-concurrency.log |
| 项目venv运行`http-check.py` | PASS，真实服务端HTTP；http-check.log |
| 项目venv运行`hygiene-check.py`（仓库根） | PASS；hygiene-final.log |

上述manage.py命令在backend运行，npm在frontend运行；完整路径、原始结果均保留在evidence/f0-04。QA初始化脚本执行正常migrate并创建管理员，不把测试库配置写入公共设置。

后端覆盖：配置独立及精度、严格输入、草稿编辑与原子名单替换、非法/重复/停用选手、有效管理员参赛、四种人数/非法人数、昵称快照、冻结/重复启动、未知状态/删除拒绝、真实CSRF、权限矩阵、数据库CHECK/唯一约束、快照写入后失败回滚、并发启动和启动与配置/名单编辑。共享内存SQLite测试与文件SQLite检查分开记录。

前端覆盖：列表加载/搜索/状态/分页、草稿表单/校验/Oka、选手分页搜索与去重、原子编辑、非法人数启动限制、启动确认/取消/成功/冲突、已启动只读、API字段错误/重试/空状态及角色菜单/路由保护。深浅主题与移动交互另由真实浏览器检查，不把jsdom当成视觉验收。

保留失败证据：初次后端全量55项中1项失败（新增选手字段改变旧契约）；恢复旧字段，改为可选eligible筛选，并新增兼容测试后最终56项通过，旧测试未修改。初次前端49项中1项因测试选择器空白匹配失败，改为真实可访问名称匹配后全通过。见backend-tests.log/frontend-tests-initial.log。QA初始化日志的Python说明文字转义警告已修正脚本；Node实验性localStorage告警仍在测试日志，未导致失败。没有隐去失败记录。

## 9. 实际HTTP与浏览器

HTTP检查使用独立CookieJar和CSRF初始化，日志不输出密码/Cookie/token：健康200；匿名赛事403；登录缺CSRF403；管理员创建201、详情/PATCH/PUT200、重复名单400、三人启动400、四种人数启动200、冻结修改与重复启动409；全部四类写操作缺CSRF403；普通用户GET/POST403；eligible选手真实第二页可读；错误名单原子编辑后名称保持原值。未执行HTTP并发负载测试。

浏览器实际：匿名跳登录；管理员创建并从第二页选3名普通选手和管理员本人；保存草稿；启动确认取消不启动；编辑为3人并验证启动禁用；搜索管理员恢复4人；确认启动后只读。规则25001/30000展示Oka19.996。搜索真实赛事、深浅主题、390px表单编辑/轮数选择、320px列表检查；320px viewport/body/main均320，无横向溢出。

主动停止后端后刷新列表，出现错误与“重新加载”，恢复同一QA库后重试成功；刷新页面保留会话；普通用户无赛事入口且直达显示无权访问。最后管理员逐页回归dashboard/players/machines/settings/profile/tournaments，健康连接正常。浏览器最终error/warn日志为空。路由清单browser-routes.json、mobile-metrics.json、browser-final-dom.txt、browser-logs.json及HTTP原始服务日志均保留。

CUA一次标题定位传入其不支持的level过滤，导致多标题匹配；重新观察DOM后改为准确标题名称，不是应用异常。可见浏览器的视口临时被宿主调整，转后台并记录稳定几何后完成手机检查。原F0-02登录后落到仪表盘的行为保留，使用实际赛事入口继续联调，未无关重构认证。

## 10. Git与敏感信息

分支main，HEAD仍`0d7e96b0b920e490abbf7acd1d4aba38493025f9`；无暂存、提交、标签、推送或远端配置更改。工作区有本阶段预期修改和新增文件，**不是干净工作区**，交由Owner后续Git操作。

git diff --check通过；旧账号/设备/公共模块、原API层、依赖锁和F0-01～03证据对baseline/F0-03无差异。所有历史迁移和Tag保留。敏感检查覆盖Git可见文件、实际本地密钥/本次随机QA密码及常见token/私钥模式，没有发现泄漏；这是定向检查，不宣称完整安全审计。

.env、.verification/凭据与数据库、虚拟环境、.tools、node_modules、dist与缓存均由git check-ignore确认忽略。证据截图是QA昵称和赛事，不包含密码、Cookie或CSRF token。

## 11. 已知限制及未验证

- **UNVERIFIED**：PostgreSQL实际迁移、连接及并发；生产部署、HTTPS、公网安全与压力测试。SQLite检查不能替代这些验证。
- 开发库未应用F0-04，为满足独立QA验证要求保持不变；Owner实际使用前需正常migrate。
- 点数整数上限/Uma64字符为工程边界；更细数值规则、TBD-001和TBD-002待Planner确认。
- 无轮次、分桌、设备分配/占用、半庄计分、排名/冠军、取消/删除/完赛、微信或团队赛；启动不产生第一轮。
- 原有公网登录限流等安全加固仍属后续任务；没有引入新身份方案。草稿并发编辑按提交顺序覆盖字段，没有额外版本冲突交互。

## 12. Developer结论

本阶段授权范围内已完成实现、迁移/回归/构建、SQLite事务并发、实际API和浏览器自检；已知未验证项如实列出。Developer自检PASS，F0-04正式基线尚未建立；停止开发，等待Planner源码审查与验收。
