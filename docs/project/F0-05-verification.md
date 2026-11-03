# F0-05 首轮分桌与麻将机分配交付及自检

日期：2026-11-03（Asia/Shanghai）。Developer自检PASS；本阶段未正式验收、未建立基线，等待Planner审查。没有commit、tag、push，没有进入成绩或计分阶段。

## 1. 文件与基线

开始时main工作区干净，HEAD及本地baseline/F0-04解引用均为`434a8aa9ae5bd075705322e0556688b7424db16a`。Owner确认F0-04 CLOSED/PASS及双端基线；本次仅实查本地引用，不冒称重新核验了GitHub远端。

新增源码：

- `backend/machines/locking.py`：共同设备锁路径。
- `backend/tournaments/migrations/0002_tournamentround_roundtable_roundseat_and_more.py`。
- `backend/tournaments/round_services.py`、`round_serializers.py`、`round_views.py`、`table_urls.py`、`tests_rounds.py`。
- `frontend/src/services/rounds.ts`、`pages/rounds.tsx`、`pages/rounds.test.tsx`。
- `frontend/src/components/round-action.tsx`、`tournament-round-summary.tsx`。
- 本报告及`docs/project/evidence/f0-05/`原始日志、截图、QA/并发/HTTP/卫生检查复现脚本。

修改models、赛事和根URL、machines.services；前端App路由、赛事详情/摘要/入口、布局/当前阶段文案、反馈和样式；AGENTS、README、requirements、architecture、roadmap、baselines。没有新增依赖或修改锁文件。

本次共96个变更文件：18个已跟踪文件修改、78个新增文件（含过程证据）。逐文件清单：[changed-files.txt](evidence/f0-05/changed-files.txt)；[Git状态](evidence/f0-05/git-status.txt)；[源码SHA256](evidence/f0-05/source-sha256.txt)。旧测试、历史迁移及F0-01～04验收证据保留。

## 2. 实体结构

| 实体 | 内容与关联 |
| --- | --- |
| TournamentRound | Tournament FK，round_number、生成时间/管理员、创建时间；不增加虚假完赛状态 |
| RoundTable | Round FK、逻辑table_number、创建时间；逻辑桌ID与设备编号分离 |
| RoundSeat | Round、RoundTable、TournamentParticipant FK，east/south/west/north、创建时间 |
| MachineAllocation | Table、稳定machineId FK；active/released、分配时间/管理员、释放时间/管理员/说明、分配时machine_no_snapshot |

FK使用PROTECT保留历史实体。Tournament继续started，不把设备释放解释为成绩或轮次完结。昵称从已冻结的TournamentParticipant快照读取，不建立新账号或选手身份。

## 3. 随机算法

`generate_first_round`读取指定started赛事冻结名单，合法人数4/8/12/16，使用标准库`random.SystemRandom().shuffle`一次，然后每四人一组，依次东、南、西、北；无固定生产种子。rng参数允许测试注入可控随机源，测试反转输入并验证完整确定性排列，不要求随机结果每次必然不同。[Python官方随机源文档](https://docs.python.org/3.13/library/random.html#random.SystemRandom)。

轮、桌、座次与所有设备占用同一事务写入，生成后持久化；刷新只读数据库结果，重复POST返回409且不覆盖原座次。不接受客户端提交整张随机分桌。

## 4. 数据库与完整性边界

- UNIQUE(tournament,round_number)，round_number CHECK 1～6。
- UNIQUE(round,table_number)，table_number CHECK 1～4。
- UNIQUE(table,seat_wind)、UNIQUE(round,participant)，wind CHECK四风。
- MachineAllocation分别条件唯一：一台machine最多一条active，一张table最多一条active；released可保留多条。
- 状态CHECK：active无released_at/released_by/释放原因；released必须有released_at/released_by。

`RoundSeat.clean`与`validate_round_structure`检查table.round_id=round_id、participant属于当前赛事、每桌恰好四风、全员本轮恰好一次、正确桌数及连续桌号、轮数不超过父赛事。跨表规则/精确人数不是普通数据库CHECK保证，不能冒称数据库已全部约束。SQL唯一约束已使用无其他唯一冲突的独立场景分别测试。

无轮次、座次、历史分配的普通编辑或DELETE接口；服务不删除分配历史。数据库管理员直接SQL/ORM绕过服务不在API完整性保证范围内。

## 5. 资源选择与并发

仅使用真实available且没有任何active分配的设备，按machine_no升序选择；现役最多四台，不限制编号001～004。不要求单赛事独占整个池，其他空闲设备仍可分给另一赛事。不足时整体409，不部分生成。

共同锁顺序：**物理设备池稳定PK升序 → 赛事行（生成）→ 新轮/桌/座次/分配或占用记录更新**。

SQLite在任何读之前执行无值改变的`UPDATE updated_at=updated_at`取得写事务预留；PostgreSQL按稳定PK顺序SELECT FOR UPDATE锁住池中已有行。只能从本次已锁行选择设备，新插入设备留待后续请求。生成、调整、释放、设备状态修改共用此路径，避免检查available之后被另一事务停用。条件唯一约束作为额外兜底。[Django行锁说明](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update)、[条件唯一约束](https://docs.djangoproject.com/en/5.2/ref/models/constraints/#uniqueconstraint)。

SQLite忙锁返回409 tournament_busy或machine_busy，不自动重放未知结果。物理池短事务串行协调适用于当前四台现役规模；历史退役行也在锁集合，规模扩大后的吞吐需另行评估。PostgreSQL代码策略尚未实连验证，不声称实际通过。

## 6. 调整、释放和状态联动

调整只适用于active桌，目标必须存在、available且无active占用；先校验再将旧记录released、写审计，然后新建active与编号快照，整个事务提交。新分配写入失败会恢复原记录为active。同机返回machine_unchanged，不能制造无意义历史。

释放填写时间、管理员和可选说明，保留原桌与座次，机器可用于其他赛事。重复释放、释放后调整/重开返回allocation_released。释放不确认成绩、不改变赛事started、不产生正式轮次完成。

machines.services保留原API输入/输出契约；新增active检查，拒绝maintenance、disabled、retired，仍允许编辑名称、位置、备注、编号等普通字段。历史编号保存在snapshot中，当前编号和原稳定machineId均可追溯；FK保留原设备身份。

## 7. API与请求示例

全部要求管理员Session，所有写请求使用原有CSRF初始化与X-CSRFToken。成功`{"data":...}`，错误`{"error":{"code":"...","message":"...","fields":{...}}}`，不输出凭据、capacity_slot或数据库异常。

| 方法 / 完整路径 | 契约 |
| --- | --- |
| GET `/api/v1/tournaments/{id}/rounds/` | data.results轮次列表，含各桌四风、快照昵称、当前分配及历史 |
| POST 同上 | `{"round_number":1}`，201；只支持第一轮 |
| GET `/api/v1/tournaments/{id}/rounds/{round_number}/` | 指定已生成轮次详情；不存在404 |
| GET `/api/v1/round-tables/{id}/` | 逻辑桌及四座、active_allocation（释放后null）、allocation_history |
| GET `/api/v1/round-tables/{id}/machine/history/` | data.results按分配时间/id升序，包含释放审计与编号快照 |
| POST `/api/v1/round-tables/{id}/machine/reassign/` | `{"machine_id":3}`，200；只调整机器 |
| POST `/api/v1/round-tables/{id}/machine/release/` | `{"reason":"本桌实体使用结束"}`，reason可省略，200 |
| GET `/api/v1/machine-resources/` | 现役物理池状态、assignable、active_allocation及所属赛事/桌，供确认前检查 |

示例ID须替换为真实查询结果。资源查询是当时快照，写入时再次检查。allocation返回machine_id、当前machine_no、machine_no_snapshot、machine_status、active/released和审计ID/时间；座次显示赛事昵称快照。

409业务码包括tournament_not_started、round_already_generated、insufficient_machines、later_round_unavailable、machine_occupied、machine_unavailable、machine_unchanged、allocation_released、machine_in_use、allocation_conflict、tournament_busy/machine_busy。非法轮号或未知/内部字段400；无权限/CSRF403；不存在404；未定义方法405。

第二至第六轮POST明确返回later_round_unavailable；不以姓名、账号或假分排序。后续轮次须等F0-06成绩确认和精确累计积分。TBD-001/002未解决。

## 8. 前端与视觉

已启动赛事详情新增真实轮次/当前设备占用摘要与工作台入口。`/tournaments/{id}/rounds`显示参赛人数、总轮数、预计桌数、已生成轮次和本赛事占用；真实资源池区分基本状态与跨赛事占用。

生成先刷新赛事/轮次/机器，再展示所需桌/设备、空闲数及持久化说明并确认。草稿无生成入口，已生成无重复入口；资源不足禁用确认并解释原因。四风和昵称清晰展示，不展示假比分或后续轮次。

调整、释放分别通过shadcn Sheet确认，显示原设备/座次、目标空闲设备或释放原因；历史可查询。忙态禁用确认和关闭，409显示业务错误、不自动重试。失败后提供刷新，避免静默重放。

沿用Riichi Premium深色/浅色和响应式样式。320px/390px检查无横向溢出；手机Sheet输入及取消正常，Escape关闭后焦点回到“查看第1桌设备历史”（keyboard-focus.json）。普通用户/匿名不能进入工作台，菜单不显示管理入口。

截图全部来自独立QA库，非正式/演示生产赛事：

- [双桌深色工作台](evidence/f0-05/rounds-desktop-dark.png)、[四桌实际生成](evidence/f0-05/four-tables-dark.png)、[亮色](evidence/f0-05/rounds-desktop-light.png)
- [分配历史](evidence/f0-05/allocation-history.png)、[释放确认](evidence/f0-05/release-confirmation.png)、[资源不足](evidence/f0-05/resource-shortage.png)
- [390px](evidence/f0-05/rounds-mobile-390.png)、[320px](evidence/f0-05/rounds-mobile-320.png)、[手机释放表单](evidence/f0-05/release-mobile-light.png)

## 9. 迁移与原库保护

开发库showmigrations显示原F0-03已应用、F0-04/0001尚未应用（migrations-before.log）。先用SQLite backup复制到被忽略的`.verification/f0-05-qa.sqlite3`，再顺序正常migrate F0-04/0001与F0-05/0002，均OK（qa-setup.log）。新增四表/约束，没有改旧迁移、fake、删库或重置。

原开发User/Profile/Machine均0行，前后开发数据库SHA256均`c4738a1eada032c19a2f9e33f2dcb555a961f1457321b5bd2ebccd92ffa3a2c9`。全部QA管理员、选手、设备、赛事及占用仅在独立库；官方createsuperuser初始化随机QA密码，仅写忽略目录，不输出凭据。

开发库保持原样，Owner实际使用前需正常migrate。启动方法仍为README两个PowerShell窗口：

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

已有管理员可跳过创建。密钥依README初始化，不使用QA密码作默认密码。访问http://127.0.0.1:5173，API为http://127.0.0.1:8000/api/v1/。验证结束QA服务/临时浏览器已关闭，8000/5173监听数0，忽略的QA证据库保留。

## 10. 自动化、类型与构建

Windows PowerShell；Python3.13.18、Django5.2.18、Node26.3.0、npm11.16.0，原依赖锁不变，无全局安装。

| 实际命令 | 结果 / 原始证据 |
| --- | --- |
| `.venv/Scripts/python.exe manage.py check` | PASS，0问题；backend-check.log |
| `manage.py migrate --noinput`（独立QA DATABASE_URL） | PASS；qa-setup.log首次应用两迁移，migrate-final.log无待迁移 |
| `manage.py makemigrations --check --dry-run` | PASS，No changes detected；migration-check.log |
| `manage.py test -v 2`（backend目录） | PASS **72/72**，原56+新增16；backend-tests-delivery.log |
| `npm run typecheck` | PASS；typecheck-delivery.log |
| `npm test` | PASS **65/65**，原49+新增16；frontend-tests-delivery-2.log |
| `npm run build` | PASS（含TS检查）；frontend-build-delivery.log |
| `npm audit --json` | PASS，0漏洞；npm-audit.json |
| venv运行`file-concurrency.py`及最终`--final` | PASS，两份独立文件各4项真实SQLite竞态；file-concurrency.log/file-concurrency-final.log |
| venv运行`http-check.py` | PASS，真实HTTP；http-check.log |
| venv运行`hygiene-check.py`（仓库根） | PASS，Git/敏感/忽略/原库检查；hygiene-final.log |

manage.py在backend执行，npm在frontend；QA脚本从backend运行，日志不打印Session/CSRF/密码。无把未运行测试标通过。

后端覆盖四种人数、四风/全员完整性、可注入随机源与持久化、重复生成、非法轮号/后续轮次、不可用/占用设备、部分分配故障全回滚、独立SQL约束、跨表不变量、调整失败原占用恢复、历史快照/稳定ID、释放终态、设备状态联动、真实CSRF、权限及所有旧回归。并发测试审计数据库最终状态，不只检查HTTP返回值。

前端覆盖真实契约加载、四种所需桌数、草稿/已生成限制、生成确认/取消/忙态、资源不足、四风渲染、空闲选择、历史、释放、409、重试/刷新恢复、不生成假积分及权限；赛事详情摘要读取真实轮次和占用。视觉由浏览器检查，不把jsdom当视觉证明。

保留失败证据：backend-tests-initial.log曾从仓库根发现0测试，未计为通过，改在backend执行完整套件；文件并发初次TEST字典覆盖缺MIRROR导致setup失败，file-concurrency-initial.log保留，修正后真实文件4项通过。前端初次2项失败：独立详情组件新增Router Link依赖、历史文字定位不唯一；改为语义a链接和对话框内断言，旧测试未改。最后TS发现测试定位器不支持exact参数，已修正；typecheck-final.log/frontend-build-final.log保留失败，最终delivery日志通过。Node实验性localStorage告警仍保留，未导致失败。

## 11. SQLite并发与实际联调

共享内存SQLite全量测试含4组并发；另以独立文件`.verification/f0-05-concurrency.sqlite3`运行同一组真实服务测试，4项通过并保留文件；最终补充“目标不在锁定池”保护后，使用另一份`f0-05-concurrency-final.sqlite3`重跑4项全部通过，未覆盖旧证据。验证同赛事只有一次生成成功、跨赛事争四台不双占、生成与停用/退役竞争、调整与生成/释放竞争。每次检查active machine/table唯一、active设备仍available、所有已生成轮次全员及座次完整。资源池快照后新出现目标的路径通过可控注入测试，真实PostgreSQL幻行竞争仍未验证。无PostgreSQL或HTTP并发压测声明。

真实HTTP：健康200、匿名资源403、草稿生成409、管理员生成201；双桌设备007/107按序、八人完整、重复生成409、GET恢复相同分桌、第二轮409；三类写操作缺CSRF403；占用设备停用/退役409；调整与释放200、释放后重复/重新分配409；历史保留、最后HTTP测试归还资源；普通用户所有新增查询及释放写入403。完整状态日志http-check.log，服务端原始日志http-server.log/http-server-final.log。

浏览器：从真实赛事详情进入双桌工作台，取消生成后重新确认；刷新座次完全一致；007调整为207并查询旧released/新active；另一12人赛事因需要3台而只有2台空闲禁用确认；取消/确认释放并检查失去调整入口；释放原双桌后16人赛事成功生成四桌。查看详情真实摘要“1轮/4台”；手机释放说明输入不提交、深浅主题、320/390无横向溢出；网络停机错误与恢复重试；普通用户无入口/直达拒绝，匿名直达跳登录；管理员回归全部基础页面与健康连接。

最终浏览器error/warn日志为空（browser-logs.json）；Escape焦点恢复、视口记录、路由与最终DOM分别保留。期间临时标签被关闭，重新打开同一持久化四桌页面并继续验证，没有重生成或丢数据。

## 12. 未验证及限制

- **UNVERIFIED**：PostgreSQL实连、迁移与并发/死锁验证，生产部署/HTTPS及公网压力测试。SQLite结果不替代这些验证。
- 设备池有序锁策略偏保守，当前仅四台现役；历史退役设备增长后的性能需另行评估，未引入复杂调度基础设施。
- 开发库未迁移，Owner使用前需正常migrate；QA数据不作为正式演示数据。
- 无成绩、Uma/Oka实际得分、累计排名/冠军、后续轮次、取消/删除/完赛或强制恢复；不解决TBD-001/002。设备释放不确认成绩、不完结轮次。
- 普通API保证完整性与历史保留，不宣称可阻止数据库管理员直接SQL绕过服务；资源查询是瞬时快照，最终写入必须重新校验。
- 原公网登录限流等加固仍属于独立任务，没有改变身份体系。

## 13. Git与安全范围

保持main，HEAD仍`434a8aa9ae5bd075705322e0556688b7424db16a`，历史四个Tag解引用均未变。无暂存、提交、标签、推送、远端配置修改。工作区有本次预期变更，不是干净工作区，详见逐文件Git状态。

git diff --check通过；原账号、选手、公共API、旧测试、历史迁移、F0-01～04证据及依赖锁无差异。定向扫描Git可见文件中的实际本地密钥/本次QA密码及常见令牌/私钥模式，无命中；不是完整安全审计。git check-ignore确认.env、虚拟环境、QA凭据/两类数据库、.tools、node_modules、缓存、dist均忽略。

## 14. Developer结论

F0-05授权范围内实现与本地自检PASS；代码、文档、失败及成功证据可供审查。F0-05未正式验收、未建立基线。停止开发，等待Planner源码审查与Owner后续Git操作，不进入F0-06。
