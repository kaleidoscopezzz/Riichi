# F0-06 Developer 交付与验证报告

日期：2026-11-04（Asia/Shanghai）。状态：**Developer 自检通过；完整未提交候选，待Planner独立验收**。不是正式CLOSED / PASS，未建立F0-06基线。

## 授权、范围与基线

工作目录D:\Riichi，分支main，开发起点HEAD `5f31891b4ae3a589057e7054758abb08ca42ec72`，初始工作区干净。D0-01已由Planner正式验收CLOSED / PASS；Owner确认文档Commit已推送且本地/远程SHA一致，本轮本地HEAD核验一致，没有重新查询远端。正式代码基线`baseline/F0-05^{commit}`为`41929da1e53f8bb481beb4ea3bc31b65f9ee86ff`，F0-05保持CLOSED / PASS。

本次一次性完成赛事固定选桌、成绩草稿/确认、精确计分、累计榜、2～6轮重排、公开抽签、唯一冠军、完赛与自动释放，并接续F0-04/F0-05数据。不新增其他赛制、取消/强制中断、已确认成绩撤销、微信、团体赛、调度平台或基础设施。没有新增依赖或改锁文件。未执行commit/tag/push，没有修改远端或历史Tag。

## 实现与模型

- machines新增0003解除四台capacity_slot CHECK，保留原列、旧值/唯一索引和稳定ID，新设备NULL；create_machine不再四槽循环，UI不再禁建第五台。现役编号唯一、状态/退役终态和占用保护保留。
- Tournament新增策略/版本/来源、首轮随机顺序/来源、资源兼容状态/审计、completed/冠军/完成管理员/时间/final_snapshot；启动冻结规则和名单，completed只读。
- TournamentTable提供稳定A～D，Reservation保存物理桌预留、替换/释放历史与OneToOne旧allocation桥接，活动机器和桌位条件唯一。RoundTable新增可空固定桌位FK和生成时设备快照；原轮桌座及分配ID不变。
- TableResult每桌OneToOne，保存部分points JSON、version、确认状态、权威scores/规则及录入确认审计。points允许整数、负数、零、空草稿；服务和API严格验证，不接受替换人员/四风或前端权威分数。整数范围±(2^53−1)，确认必须四人及总和4×开局，确认后锁定。
- LotteryRecord记录组员、完整结果顺序、方式、过程、实际抽签时间、来源成绩版本、记录/确认管理员及时间。记录与确认是独立POST，不后台抽取结果，不以首轮顺序暗定冠军。
- TournamentRound.generation_snapshot记录规则、来源成绩版本、排序名单及首轮序列引用。新首轮显式machine_ids顺序即A～D；后续只重排选手/四风，不重新选桌。
- 逻辑在scoring.py和competition_services.py，View只处理管理员权限、严格输入和data/error响应。前端分为工作台、操作Sheet、榜单及类型化服务，保留账号/选手/设备/赛事既有能力和旧历史只读入口。

## 精确计分、排序与冠军

TBD-001 / split_rank_bonus_v1、TBD-002 / performance_v1和OP-01～05均RESOLVED，规则未改变。后端全程Fraction：Uma十进制字符串直接解析，Oka、同点均分、累计和比较不经过float或有限精度舍入。数据库JSON和API保存规范化分子/正分母字符串，例如`{"numerator":"50","denominator":"3"}`，可无损重建。前端用BigInt生成两位展示近似值，同时给出精确值，不进行权威累计或排序。

正常奖励[50,10,-10,-30]，三人并列第一50/3各自无损保留；并列用组首名次，1/2次数按共享名次计，不将并列第一再计第二。自定义Uma非零和不修正，默认总和性质按规范条件成立。每场冻结两个策略标识和rules_version=1，未知策略/版本拒算，不动态执行表达式。

后续分桌按累计、第一次数、第二次数、从最近向前逐轮积分，完全相同才按持久化首轮顺序；每4人一组，新组四风重新随机并持久化。冠军/最终名次没有首轮或ID兜底，所有仍完全相同组分别公开抽签、二次确认。完赛事务固定全体排名、唯一冠军、规则/来源版本/抽签引用并只释放本赛事资源；任何失败整体回滚。

## 非破坏性迁移与 Owner 数据保护

开发前只读showmigrations显示Owner库已应用accounts/players/machines基础迁移，tournaments0001/0002尚未应用；没有擅自迁移Owner库。SQLite backup创建忽略目录`backend/.verification/f0-06/owner-copy.sqlite3`，只在该副本正常migrate到新版本。原库SHA256前后一致：

`c4738a1eada032c19a2f9e33f2dcb555a961f1457321b5bd2ebccd92ffa3a2c9`

新增tournaments0003结构、0004数据迁移；旧迁移未改。0004回填`legacy_default_backfill:0004`及来源时间，按旧桌号/东南西北恢复首轮随机序列，建立固定桌位和active桥接，不改变任何旧列（含updated_at）、数字配置/名单、原座次或旧分配状态。桥接时间明确表示升级接入时间，不伪造当年的人工选桌。

[带数据迁移复验](evidence/F0-06/migration-compatibility-v3.txt)通过。比较5台机器（含退役/编号复用）、4赛事、24参赛记录、3轮、5桌、20座次、5分配的所有旧列，数量/主键/关系/快照/历史完全一致。覆盖：F0-04启动未分桌unselected、F0-05完整active自动fixed、partial/released标review_required。3个有效active均桥接；继承占用不额外要求人工采纳，released不会复活。

独立复核验证：保留有效占用后补选空闲机器；已释放且全部配置轮次存在可historical_only后补历史成绩并正常完赛，无需临时占桌；他场占用不得自动抢回。旧adjust/release发现固定桌位即409，原历史GET保留；新旧占用并集参与所有资源状态检查和互斥。旧生成代码仅保留为不被运行时导入的legacy_test_fixture，用于构造历史回归数据。

部署升级须暂停旧版本服务写入。0004数据迁移故意不可逆，避免取消桥接后暴露占用；正式数据库回退需停写、保留备份和单独部署方案，不fake/删库。真实PostgreSQL升级尚UNVERIFIED。

## API契约

根路径`/api/v1`。所有下表接口均IsAdminUser + Django SessionAuthentication；写请求须先GET `/auth/csrf/`取得当前token，携带Session Cookie与X-CSRFToken。不得记录两者。成功`{"data":...}`，错误`{"error":{"code":"...","message":"...","fields":...}}`。403用于匿名/普通用户/无效CSRF；未知字段/类型/点数或身份集合错误400；不存在404；业务竞争/冻结409；不支持方法405。health仍匿名且维持原响应。

| 方法 / 路由 | 请求 / 成功数据 |
| --- | --- |
| GET `/machine-resources/` | data.results含machine_id/no/name/status、assignable、旧active_allocation及新reservation（tournament_id/name/ordinal）；状态available不等于可分配 |
| POST `/tournaments/{id}/rounds/` | 首轮`{"round_number":1,"machine_ids":[2,3,5,7]}`明确A～D；后续`{"round_number":2}`。201返回持久化round（含tables/seats/result/machine_snapshot/generation_snapshot） |
| GET `/tournaments/{id}/rounds/` | data.results完整已生成轮次，支持completed历史 |
| GET `/tournaments/{id}/rounds/{number}/` | 单轮同上；不重排、不写入 |
| GET `/round-tables/{id}/` | 原id/round/table_number/seats/旧allocations，加tournament_table_id、生成设备快照、result |
| GET `/round-tables/{id}/result/` | table_id/version/status/points/scores/rules/edited_by/at/confirmed_by/at；未存时version0、空草稿 |
| PUT `/round-tables/{id}/result/` | `{"version":0,"points":[{"participant_id":21,"raw_points":-1000},{"participant_id":22,"raw_points":0}]}`替换当前部分草稿；可缺项或null，未知/重复/他桌ID拒绝。成功version递增 |
| POST `/round-tables/{id}/result/confirm/` | `{"version":1}`确认已存草稿；也可携带完整points。必须四人整数且总和正确，保存完整score和规则/audit后锁定 |
| GET `/tournaments/{id}/workspace/` | resource_state、mapping及预留历史、compatibility_audit/order_source、lotteries、实时standings/unresolved_groups/ready/all_results_confirmed/source_versions/rules；completed返回冻结最终快照及champion_id/completed_at/by |
| POST `/tournaments/{id}/tables/replace/` | `{"ordinal":1,"machine_id":6,"reason":"实体故障"}`，原子结束旧预留并建立新预留，逻辑桌不变。返回mapping |
| POST `/tournaments/{id}/compatibility-review/` | `{"historical_only":false,"machine_ids":[2,6],"reason":"复核说明"}`或historical_only=true且machine_ids=[]；只对review_required有效。返回mapping |
| POST `/tournaments/{id}/lotteries/` | `{"members":[21,22],"order":[22,21],"method":"公开签条","description":"现场过程","drawn_at":"2026-11-04T03:00:00Z","source_versions":[{"table_id":10,"version":2}]}`。201返回完整记录，尚未确认，不用于完赛 |
| POST `/tournaments/{id}/lotteries/{lottery_id}/confirm/` | `{"confirmed":true}`，验证组员、版本和状态，写confirmed_by_id/confirmed_at；重复409 |
| POST `/tournaments/{id}/complete/` | `{"confirmed":true,"source_versions":[{"table_id":10,"version":2}]}`，来源必须准确覆盖当前全部确认结果。返回冻结standings/champion_id/rules/source_versions/lottery_ids/completed_at/by，自动释放本场资源 |
| GET `/round-tables/{id}/machine/history/` | 原始分配历史不变；旧reassign/release POST仍可追溯，但赛事已桥接/固定时409 fixed_reservation_protected，不能绕过预留 |

示例ID只是契约示意，实际客户端必须用当前API返回的稳定ID、完整source_versions和选手集合，不能拷贝示意结果当真实比赛数据。workspace当前最多16人，不需要额外榜单分页；已有赛事列表仍支持page/search/status（新增completed）。原身份/机器/赛事API沿用。

权威scores每项包含participant_id、raw_points、rank、tied、base、bonus、score（后三项均有理数对象）。standings含participant_id/display_name快照、rank、total、confirmed_rounds、first_count/second_count、rounds（逐轮原始点数/共享名次/奖励/单场积分和轮桌ID）；临时并列保持共享rank。最终快照冻结每位选手这些字段及lottery引用。抽签记录使用created_by_id/confirmed_by_id及时间，结果ID不冒充旧MachineAllocation ID。

主要409码：tournament_not_started、round_already_generated、round_not_next、results_incomplete、resource_review_required、machine_unavailable、machine_occupied、machine_unchanged、stale_result、result_locked、round_locked、stale_standings、lottery_required、lottery_conflict、competition_conflict、tournament_busy、fixed_reservation_protected。请求失败后界面提示关闭/刷新核对，不自动重放写入。

## 实际自动化与构建

环境：Windows PowerShell；Python3.13.18，Django5.2.18，DRF3.18.3；Node26.3.0 / npm11.16.0，依赖沿用精确锁。后端命令工作目录D:\Riichi\backend，前端D:\Riichi\frontend。命令中DATABASE_URL仅QA副本，不能省略后对Owner库运行迁移。

```powershell
# backend（独立副本）
$env:DATABASE_URL='sqlite:///D:/Riichi/backend/.verification/f0-06/owner-copy.sqlite3'
.\.venv\Scripts\python.exe -X utf8 manage.py check
.\.venv\Scripts\python.exe -X utf8 manage.py migrate --noinput
.\.venv\Scripts\python.exe -X utf8 manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -X utf8 manage.py test --verbosity 1
.\.venv\Scripts\python.exe -m pip check

# 带历史数据新QA库（每次新的文件路径，不删除/重置旧库）
$env:DATABASE_URL='sqlite:///D:/Riichi/backend/.verification/f0-06/migration-fixture-v3.sqlite3'
.\.venv\Scripts\python.exe -X utf8 -m verification.migration_check

# 真实文件SQLite（Django只创建/销毁此专用测试库）
$env:DATABASE_URL='sqlite:///D:/Riichi/backend/.verification/f0-06/owner-copy.sqlite3'
$env:TEST_DATABASE_NAME='D:/Riichi/backend/.verification/f0-06/concurrency-complete.sqlite3'
.\.venv\Scripts\python.exe -X utf8 manage.py test tournaments.tests_competition.CompetitionConcurrencyTests tournaments.tests_rounds.ConcurrentRoundTests machines.tests.ConcurrentMachineTests --settings=verification.settings --noinput --verbosity 2

# frontend
npm run typecheck
npm run test -- --reporter=dot
npm run build
npm audit --json
```

| 检查 | 实际结果 / 原始证据 |
| --- | --- |
| Django check | PASS，0问题；[日志](evidence/F0-06/check-final.txt) |
| 正常migrate | PASS，Owner副本及空QA库正常前向迁移；[QA初次迁移](evidence/F0-06/qa-migrate.txt)、[最终状态](evidence/F0-06/migrate-final.txt) |
| makemigrations --check --dry-run | PASS，No changes detected；[日志](evidence/F0-06/makemigrations-final.txt) |
| Django全量 | **97 / 97 PASS**；[最终日志](evidence/F0-06/backend-complete.txt)。原72项保留并调整冲突断言，新增25项覆盖完整工作流/精度/资源/并发等 |
| 文件SQLite并发 | **12 / 12 PASS**；[日志](evidence/F0-06/file-sqlite-complete.txt)，独立真实磁盘库，非仅Mock/内存 |
| TypeScript | PASS；[日志](evidence/F0-06/typecheck-final.txt)，最终build再次typecheck |
| Vitest | **73 / 73 PASS**，7文件；[日志](evidence/F0-06/frontend-complete.txt) |
| Vite生产构建 | PASS；[日志](evidence/F0-06/build-complete.txt)，2195模块，JS428.65KB/gzip133.15KB |
| npm audit | PASS，全部等级0漏洞；[原始JSON](evidence/F0-06/npm-audit.json) |
| pip check | PASS，No broken requirements found；未修改依赖 |
| 带数据迁移 | PASS，所有原列不变/有效继承/异常复核；[日志](evidence/F0-06/migration-compatibility-v3.txt) |

完整服务链覆盖4人1轮、8人3轮、12人2轮、16人6轮、跨赛事资源竞争和完赛后复用；每轮每人一次/四风完整、冻结设备沿用。精度覆盖所有并列组合、50/3三轮累积、长小数Uma、不同开局/非零和Uma、DB/JSON往返、负数/零/异常总和及草稿不计分。

故障注入在真实事务中分别使首轮座次写入、计分、故障新预留、完赛释放失败，验证轮桌座/预留/确认结果/completed快照全部回滚，不删失败用例。[测试实现](../../backend/tournaments/tests_competition.py)中对应failure_rollbacks测试。文件SQLite覆盖同轮重复、新旧资源争用、设备状态、故障换桌争用、确认/下一轮、确认/完赛、重复确认/完赛及释放/复用竞争。服务正常返回409锁忙/前置冲突，无不确定写入自动重试。PostgreSQL未连接，**UNVERIFIED**。

## 真实 HTTP、浏览器与响应式

独立忽略库`http-browser.sqlite3`正常migrate，使用随机QA管理员密码（只写忽略credentials.json，不进入日志/Git），16个真实注册档案、7张机器。QA不触碰Owner库，也没有默认生产密码。

```powershell
# backend QA服务
$env:DATABASE_URL='sqlite:///D:/Riichi/backend/.verification/f0-06/http-browser.sqlite3'
$env:CSRF_TRUSTED_ORIGINS='http://127.0.0.1:5176,http://127.0.0.1:8016'
.\.venv\Scripts\python.exe -X utf8 manage.py runserver 127.0.0.1:8016 --noreload
# frontend另窗口
$env:API_PROXY_TARGET='http://127.0.0.1:8016'
npm run dev -- --port 5176
# backend HTTP联调（读取忽略QA凭据，不打印）
.\.venv\Scripts\python.exe -X utf8 -m verification.http_check
```

真实HTTP最终运行190次请求（含CSRF初始化），创建16人6轮赛事#3，24桌确认；负数/零合法，未知/缺选桌400、重复写409，Session/CSRF缺失403。确认后生成2～6轮，固定映射未变；公开抽签（按实际并列组需要），唯一冠军、完赛自动释放和刷新一致；退出后访问403。[最终HTTP日志](evidence/F0-06/http-final.txt)。首次独立HTTP赛事#1的194请求证据也保留，不覆盖。

真实浏览器另建赛事#2，从创建草稿、选择全部16个真实QA档案、六轮配置、启动，到选A=002/B=003/C=005/D=007、首轮、部分负数/零草稿保存/刷新恢复、24桌成绩确认及2～6轮重排全部通过。为覆盖全同冠军决胜，本场正式成绩均25000；16人绩效完全相同，管理员录入公开抽签模拟所得完整倒序，保存记录后另行二次确认，冠军为QA“验收选手16”，正式完赛后四桌释放。全部是隔离QA数据，不是真实赛事或演示成绩写入开发库。

[浏览器操作证据](evidence/F0-06/browser-checks.txt)、[第四轮状态](evidence/F0-06/browser-round4.txt)、[完赛DOM](evidence/F0-06/browser-completed.txt)。刷新保持冠军/座次/最终排名，已确认和completed只读。深色1440×1000桌面、浅色390×844、深色320×740均检查；页宽不超过视口，历史面板可操作，Escape关闭并恢复触发按钮焦点，控制台无error/warn。日期控件自动填充需要键盘上下键触发原生change，未绕过应用或直接改状态。

截图：[桌面冠军](evidence/F0-06/completed-desktop-dark.png)、[390浅色](evidence/F0-06/completed-mobile390-light.png)、[320深色](evidence/F0-06/completed-mobile320-dark.png)、[320历史](evidence/F0-06/history-mobile320-light.png)。页面数据来自真实API并持久化。原账号、选手、健康、菜单/守卫、主题和响应式能力继续保留。

## 权限、CSRF与敏感信息

新增管理接口统一管理员Session，普通用户和匿名均403；写操作真实CSRF缺失/无效403，严格拒绝未知字段、bool/float/字符串点数、重复/其他桌选手、前端权威分数。服务端计算积分与冠军，前端不承担权限判定。原账号/身份配置未改，无Cookie/token/密码写日志或localStorage。

[敏感信息与保护检查](evidence/F0-06/security-and-protection.json)：所有候选文本对照本地真实配置/QA凭据字面扫描无泄漏，忽略路径检查PASS（.env、数据库、venv、QA、node_modules、dist、缓存和运行时）；依赖锁、身份/公共配置、旧迁移、原报告/证据未改。QA账户密码仅随机生成且只落忽略目录。Git未暂存，没有提交密钥、数据库、依赖或构建产物。

## 旧断言更新与失败证据

| 旧测试 / 旧假设 | 更新理由与替代回归 |
| --- | --- |
| machines.tests第五台409、四台并发上限 | 新需求允许5张以上；改为第五台201、8张NULL legacy槽及并发现役编号唯一。退役只读/编号复用原断言保留 |
| capacity_slot非NULL/1～4/retired NULL CHECK | 该容量CHECK已按新迁移解除，旧legacy列唯一索引仍保留并单独验证；状态/编号/名称等有效CHECK断言保留 |
| tests_rounds自动按编号选机、API缺machine_ids成功 | 改为显式选择所需台数并核验机器快照；缺选桌400另有HTTP/API契约回归。其余历史座次/分配/权限/回滚/并发继续保留，用fixture重建F0-05数据 |
| 后续轮一律later_round_unavailable | 改为前轮/连续性约束，未有首轮请求2～6返回round_not_next；新增完整6轮及前轮未确认409 |
| machines前端容量满禁建 | 改为超过四台仍可创建，说明单场最多四张，保留原CRUD/权限测试 |
| rounds前端首轮/自动选机/每轮释放界面 | 改为完整比赛工作台测试：显式选桌/预览/取消、4种人数、重复提交禁用、持久化四风、API错误/恢复、草稿/确认、下一轮、故障替换、旧分配历史、抽签/完赛、路由守卫与摘要；有效交互覆盖保留并扩展 |

原F0-01～05证据完全保留。本轮新增失败原始日志也保留：

- [首次后端回归](evidence/F0-06/backend-regression-initial.txt)：72项、7个旧断言冲突（容量和旧首轮行为），按上表更新，不删有效测试。
- [首次前端回归](evidence/F0-06/frontend-regression-initial.txt)：65项、16项旧页面/容量断言失败，更新API mock和新完整流程断言。
- [精度测试预期修正](evidence/F0-06/backend-second-run.txt)：1项测试把Oka20误写为30，校正测试公式后通过，没有改业务规则。
- [迁移检查初次工具错误](evidence/F0-06/migration-compatibility.txt)：Django SQLite introspection解析表结构异常，改用PRAGMA读取原列；保留旧QA库。
- [迁移旧列漂移失败](evidence/F0-06/migration-compatibility-final.txt)：发现auto_now更新旧updated_at；修复新迁移仅保存新增字段，在新的v3库比较全部旧列通过。
- [内存并发补测](evidence/F0-06/backend-final.txt)：相关请求可能分别锁忙/前置条件失败，原“至少一个成功”预期过严。新断言接受明确409并核对落库状态，再由测试显式读取/恢复；同操作重复写仍要求最多一个成功，文件SQLite独立实测通过。业务代码没有重试机制。
- [最初命令位置失误](evidence/F0-06/backend-first-run.txt)：在仓库根运行Django发现0测试，不计为PASS；随后切backend运行真实97项。

## 限制、风险与停止结论

- PostgreSQL实连迁移/并发、正式数据全量升级、生产HTTPS/安全Cookie/限流/备份部署：**UNVERIFIED**。本地SQLite与锁代码不替代生产验证。
- 本轮使用Owner副本、构造的真实历史迁移库及独立QA库；Owner原库没有实际升级。上线前须停旧进程写入，先做正式备份和副本核验。
- 原始点数工程上限定安全整数；已确认成绩不开放撤销/纠错，completed结果只读。没有取消/提前完赛/微信/团体赛，均为已确认边界。
- Node26测试环境输出实验性localStorage提示，Vitest实际通过，浏览器控制台无此提示；没有认证资料落localStorage。
- 没有F0-06正式Commit/Tag/远程候选。本次完成后停止，等待Owner Git操作及Planner独立源码验收；Developer自检不能代替正式CLOSED / PASS。

## 变更文件与Git状态

完整逐文件清单与最终检查结果由下节及审计证据列出；Git保持main，HEAD仍为批准文档Commit，所有变更未暂存。历史Tag/远端配置未变，原始数据库与历史证据保护检查通过。

本轮共 **89** 个变更文件（33个原文件修改、56个新增源码/迁移/测试/文档及证据文件）。未暂存、无删除；完整[逐文件清单](evidence/F0-06/changed-files.txt)和[Git状态](evidence/F0-06/git-final.txt)。[文档审计](evidence/F0-06/document-checks.json)通过，141个本地链接及锚点、过时状态术语与git diff --check已核对。所有失败证据保留。

```text
 M AGENTS.md
 M README.md
 M backend/machines/models.py
 M backend/machines/services.py
 M backend/machines/tests.py
 M backend/tournaments/models.py
 M backend/tournaments/round_serializers.py
 M backend/tournaments/round_services.py
 M backend/tournaments/round_views.py
 M backend/tournaments/serializers.py
 M backend/tournaments/table_urls.py
 M backend/tournaments/tests_rounds.py
 M backend/tournaments/urls.py
 M docs/F0-06-functional-spec.md
 M docs/architecture.md
 M docs/project/baselines.md
 M docs/requirements.md
 M docs/roadmap.md
 M frontend/src/components/round-action.tsx
 M frontend/src/components/tournament-editor.tsx
 M frontend/src/components/tournament-round-summary.tsx
 M frontend/src/layouts/app-layout.tsx
 M frontend/src/pages/dashboard.tsx
 M frontend/src/pages/machines.test.tsx
 M frontend/src/pages/machines.tsx
 M frontend/src/pages/placeholder.tsx
 M frontend/src/pages/rounds.test.tsx
 M frontend/src/pages/rounds.tsx
 M frontend/src/pages/settings.tsx
 M frontend/src/pages/tournaments.tsx
 M frontend/src/services/rounds.ts
 M frontend/src/services/tournaments.ts
 M frontend/src/styles/globals.css
?? backend/machines/migrations/0003_remove_mahjongmachine_machine_active_capacity_slot.py
?? backend/tournaments/competition_services.py
?? backend/tournaments/competition_views.py
?? backend/tournaments/legacy_test_fixture.py
?? backend/tournaments/migrations/0003_lotteryrecord_tableresult_and_more.py
?? backend/tournaments/migrations/0004_legacy_compatibility.py
?? backend/tournaments/scoring.py
?? backend/tournaments/tests_competition.py
?? backend/verification/__init__.py
?? backend/verification/http_check.py
?? backend/verification/migration_check.py
?? backend/verification/seed_qa.py
?? backend/verification/settings.py
?? docs/project/F0-06-verification.md
?? docs/project/evidence/F0-06/backend-complete.txt
?? docs/project/evidence/F0-06/backend-final.txt
?? docs/project/evidence/F0-06/backend-first-run.txt
?? docs/project/evidence/F0-06/backend-full.txt
?? docs/project/evidence/F0-06/backend-regression-initial.txt
?? docs/project/evidence/F0-06/backend-second-run.txt
?? docs/project/evidence/F0-06/browser-checks.txt
?? docs/project/evidence/F0-06/browser-completed.txt
?? docs/project/evidence/F0-06/browser-round4.txt
?? docs/project/evidence/F0-06/build-complete.txt
?? docs/project/evidence/F0-06/build-final.txt
?? docs/project/evidence/F0-06/changed-files.txt
?? docs/project/evidence/F0-06/check-final.txt
?? docs/project/evidence/F0-06/completed-desktop-dark.png
?? docs/project/evidence/F0-06/completed-mobile320-dark.png
?? docs/project/evidence/F0-06/completed-mobile390-light.png
?? docs/project/evidence/F0-06/document-checks.json
?? docs/project/evidence/F0-06/file-sqlite-complete.txt
?? docs/project/evidence/F0-06/file-sqlite-concurrency.txt
?? docs/project/evidence/F0-06/file-sqlite-final.txt
?? docs/project/evidence/F0-06/frontend-complete.txt
?? docs/project/evidence/F0-06/frontend-final.txt
?? docs/project/evidence/F0-06/frontend-regression-initial.txt
?? docs/project/evidence/F0-06/frontend-second-run.txt
?? docs/project/evidence/F0-06/git-final.txt
?? docs/project/evidence/F0-06/history-mobile320-light.png
?? docs/project/evidence/F0-06/http-final.txt
?? docs/project/evidence/F0-06/http-workflow.txt
?? docs/project/evidence/F0-06/makemigrations-final.txt
?? docs/project/evidence/F0-06/migrate-final.txt
?? docs/project/evidence/F0-06/migration-compatibility-final.txt
?? docs/project/evidence/F0-06/migration-compatibility-v3.txt
?? docs/project/evidence/F0-06/migration-compatibility.txt
?? docs/project/evidence/F0-06/npm-audit.json
?? docs/project/evidence/F0-06/preflight.txt
?? docs/project/evidence/F0-06/qa-migrate.txt
?? docs/project/evidence/F0-06/security-and-protection.json
?? docs/project/evidence/F0-06/typecheck-final.txt
?? frontend/src/components/competition-action.tsx
?? frontend/src/components/competition-standings.tsx
?? frontend/src/services/competition.test.ts
?? frontend/src/services/competition.ts
```
