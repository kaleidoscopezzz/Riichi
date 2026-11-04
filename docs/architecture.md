# Riichi 架构与 F0-06 兼容实现

状态：F0-01～F0-05正式CLOSED / PASS；D0-01正式CLOSED / PASS，文档Commit `5f31891b4ae3a589057e7054758abb08ca42ec72`。F0-06候选 `b9e83bb0c8e31ab660b37e7e0a46c1f0bb424e65` 已通过Planner源码/测试证据审查；当前UAT-FIX-01整改，未建立正式基线。业务规则以[统一功能规范](F0-06-functional-spec.md)为准，实际验证见[交付报告](project/F0-06-verification.md)。

## 技术与模块（当前实现）

前后端分离、模块化单体。Python 3.13 / Django 5.2 LTS / DRF；React / TypeScript / Vite / Tailwind / shadcn/ui / Lucide；SQLite开发，PostgreSQL配置与驱动预留。没有新基础设施或依赖。

| 模块 | 职责 |
| --- | --- |
| backend/config、common | 环境配置、匿名health、统一data/error JSON与中间件 |
| backend/accounts、players | AbstractUser、OneToOne选手档案、原子内部选手身份创建、仅管理员Session/CSRF、管理员资料及选手CRUD/归档 |
| backend/machines | 物理桌台账、现役编号唯一、退役终态、共用资源池锁；不限制店内四台 |
| backend/tournaments | 独立赛事、冻结规则/名单、固定选桌、轮次/四风、成绩/计分/累计/冠军/公开抽签/完赛 |
| tournaments/scoring.py | v1策略校验、Fraction计分及无损JSON转换 |
| tournaments/competition_services.py | 比赛事务、资源桥接/复核、排名、连续轮次、抽签和完赛 |
| tournaments/competition_views.py | 严格输入、IsAdminUser、DRF Session/CSRF及响应，不在View计算分值 |
| backend/verification | 独立QA迁移比较、文件SQLite测试设置、真实HTTP与QA初始化工具 |
| frontend/src/pages/rounds.tsx | 比赛工作台数据读取、轮次浏览、固定桌/成绩状态与流程入口 |
| frontend/src/components/competition-action、competition-standings | shadcn Sheet操作确认与表单、真实累计/最终榜、精确值说明 |
| frontend/src/services/competition.ts | 类型化API及仅用于显示的BigInt小数近似；不排序或累计权威分值 |
| docs/project/evidence | 分阶段不可覆盖的原始验证、失败日志、HTTP/浏览器证据 |

主要路由保留/dashboard、/tournaments、/tournaments/:id/rounds、/players、/machines、/profile、/settings及公开/login、/register。比赛工作台包含成绩、累计榜、公开抽签、完赛与历史查询，不另设复杂调度控制台。

Vite同源/api代理到Django；HttpOnly Session Cookie，前端写前取当前CSRF，密码/会话/Token不写localStorage或日志。关闭的注册端点及登录/退出继续显式csrf_protect；业务服务端IsAdminUser，DRF写请求校验Session/CSRF。成功data，错误error(code/message/fields)；health保留原契约。无全局CORS，生产需独立密钥、HTTPS、安全Cookie及登录限流。

## 领域与持久化

| 实体 | 实现和约束 |
| --- | --- |
| MahjongMachine | 原ID/编号/状态/历史保留；capacity_slot为nullable只读legacy列，旧值及唯一索引保留，新设备NULL；现役三位编号唯一、状态/名称CHECK仍有效 |
| Tournament | draft/started/completed，数字规则/Uma字符串、两个策略ID/rules_version/rules_source；revision、首轮序列/来源、资源兼容状态/审计、冠军FK、完成管理员/时间及final_snapshot |
| TournamentParticipant | 关联PlayerProfile；赛事内player唯一、启动时昵称快照，完赛仍用快照 |
| TournamentTable | 全赛事稳定逻辑桌ordinal 1～4/A～D；赛事内ordinal唯一，范围CHECK |
| TournamentMachineReservation | active/released、稳定machineId、编号快照、操作者/时间/原因、可空OneToOne legacy_allocation；active机器和逻辑桌分别条件唯一、释放审计CHECK |
| TournamentRound | 1～6且赛事轮号唯一；generation_snapshot保存规则、来源成绩版本、排序输入、首轮顺序引用 |
| RoundTable | 保留原ID/table_number，新增可空TournamentTable FK和生成时machine_snapshot；故障替换不改旧快照 |
| RoundSeat | 原Round/Table/Participant FK、桌内四风唯一、轮内选手唯一；全员及跨FK归属由服务验证 |
| MachineAllocation | 原轮次级表和全部FK/历史保留，原active条件唯一及release审计CHECK保留；新轮不复制active旧分配 |
| TableResult | 每桌OneToOne；draft/confirmed、version、points JSON（participant ID→有符号整数/空值）、scores、规则快照、录入/确认管理员及时间；确认状态CHECK |
| LotteryRecord | 赛事、来源成绩版本、组员、完整顺序、方式/过程/实际抽签时间、记录/确认管理员与时间、规则版本 |

成绩请求只引用本桌既有participant ID，不接受换座、权威积分或冠军字段。草稿允许缺项/空值；确认必须四人整数、总和4×开局且版本匹配。原始点数范围为±(2^53−1)，保证JSON到浏览器均为精确整数；超范围明确400，不截断。结果确认后无修改/撤销入口。默认未存成绩version=0，首次成功写入为1，之后成功写入递增。

所有权威奖励、基础分、累计和比较采用Fraction，从整数或精确Uma十进制字符串构造。JSON和数据库保存规范化`{"numerator":"50","denominator":"3"}`，分子/正分母均为字符串，不经float或有限精度舍入。v1只接受`split_rank_bonus_v1` / `performance_v1` / rules_version=1，未知版本拒绝计算；不执行动态表达式。

累计来自已确认结果；metric按总分、第一次数、第二次数、逆序单场积分比较。后续分桌才追加首轮持久化顺序，组内重新随机四风。最终完全同分各组必须公开抽签、保存后另行确认；不能以ID/首轮顺序暗定名次。完赛final_snapshot冻结全体结果、唯一冠军、规则和来源版本、抽签引用及操作审计，读取不重算历史。

## 事务与资源互斥

所有新写入统一使用**物理池稳定PK→赛事revision写锁→子记录**。SQLite先no-op UPDATE取得写事务；PostgreSQL按PK select_for_update。成绩也用同一顺序，避免确认/生成/完赛反序死锁。保留唯一/CHECK兜底，跨表归属、四人完整性和新旧占用互斥属于服务事务检查，不冒称普通CHECK能跨FK保证。

`occupied_ids`取Reservation active与MachineAllocation active并集，设备维护/停用/退役也检查两者；只使用已锁池中的机器。新首轮必须提交恰好人数/4个不重复machine_ids，按管理员预览顺序映射A～D，预留/序列/轮桌座原子提交。后续不再选桌、释放或复制active旧分配。

故障替换要求空闲可用目标和原因，结束旧预留、建立新预留；有legacy引用时只在真实替换/完赛写旧释放审计。旧单轮释放/调整接口发现赛事固定桌位即409拒绝，不能绕过预留约束。所有旧历史GET接口继续可读；ID空间不混用。

下一轮须连续、上一轮每桌全部确认且全员完整，重复/跳轮/草稿返回409；保存生成输入后原子写轮次/座次。完赛重新检查所有配置轮次、全部已确认成绩、来源版本、抽签及唯一冠军；同一事务保存completed/快照并仅释放本场预留及需结束的本场旧active。失败整体回滚；网络失败或409不会自动重放写请求。

## 兼容与迁移（已实现，QA验证）

1. 开发前只读检查Owner库迁移图及SHA256，SQLite backup到忽略目录；不迁移Owner库。所有验证在独立QA库及副本。
2. 新增machines/0003仅移除machine_active_capacity_slot容量CHECK，保留旧列/值/主键。create_machine同步移除四槽循环，UI移除四台上限。原0001/0002不改。
3. 新增tournaments/0003扩展字段及实体，保留原始轮桌座/分配表。0004回填`legacy_default_backfill:0004`规则来源及迁移时间，不修改任何旧列（包含updated_at）、数字配置、名单或座次。
4. F0-04已启动无首轮保持unselected，按新选桌流程接续。F0-05按旧桌号及东南西北恢复first_round_order，order_source=legacy_table_wind_v1，不重抽也不用记录ID。
5. 原active全部有效时建立稳定A～D及OneToOne legacy Reservation桥接，resource_state=fixed，直接继承。桥接的created_at表示升级接入时间，source/legacy FK及原分配时间明确可追溯，不伪造历史手动选桌。
6. 部分/全部released、机器异常或结构不完整标review_required，不恢复released、不自动抢回旧桌；仍有效的active同时桥接以保护资源池。管理员显式说明并补选空闲映射；全部配置轮次已存在且无需实体对局可确认historical_only，补历史成绩后正常完赛，不临时抢占物理桌。
7. 源码升级期间必须停止旧进程写入；数据库不能以跨表普通CHECK阻止旧二进制直接写表。当前所有对外资源写入统一检查新旧占用，保留旧接口保护，未桥接active也参与互斥。
8. 带数据QA比较所有旧列、数量、稳定ID/关系/座次/历史，验证有效继承、partial/released复核及新旧互斥。原始日志及迁移失败/修复证据见交付报告。0004不可逆，避免倒退到无桥接保护；回退须停写并按部署备份方案处理，不fake/删库。

## 历史边界与验证限制

F0-05当时是最多四台、轮次级自动选机、仅首轮、无成绩/冠军；原报告/失败证据与历史Tag保留。旧自动生成器仅在`legacy_test_fixture.py`供历史数据回归构造，运行时路由/服务不引用；正常入口只接受显式选桌。与新需求冲突的旧断言已逐项更新并补回归，有效旧权限/数据约束/历史测试继续执行。

文件SQLite并发、故障回滚、真实HTTP及16人6轮浏览器闭环的实际结果以交付报告为准。PostgreSQL实连迁移/并发、生产HTTPS部署及公网安全仍 **UNVERIFIED**；不将有序锁设计当成生产验证通过。F0-06后仅集成测试、部署、安全加固、发布验收；微信/团体赛不属V1.0。

## UAT-FIX-01 账号与选手维护兼容

不新增实体或迁移。PlayerProfile仍OneToOne User，信号仍原子建档；新选手由players/services.py生成唯一player_UUID用户名、set_unusable_password并明确非staff/superuser，昵称单独保存。既有普通User/档案不强制重建或改密码，但登录接口禁止非staff，后台API（含me/个人资料）要求IsAdminUser，公开注册端点在CSRF校验后固定403。管理员自身档案保留，仅用于后台显示资料，不作为新参赛候选。

玩家列表/详情返回id/nickname/is_active/reference_count/can_delete/创建更新时间，不含内部用户名/密码。昵称搜索和active/archived筛选、page分页，eligible=true始终排除归档与管理员。编辑、归档、恢复先User写预留/锁，再Profile锁，匹配赛事名单校验User→Profile顺序；SQLite首个写语句在读取状态前取得写事务。

删除先查任意TournamentParticipant引用，有引用409且不写历史；无引用只删业务Profile并停用User，保留用户级审计，不做User级联删除。归档使用User.is_active=False，新赛事选人与启动校验拒绝；不改已启动冻结名单/昵称、RoundSeat、成绩、排行榜或冠军。管理员档案CRUD返回受保护冲突，不会误归档/删除系统管理员。

init_admin仅在Owner明确命令调用时读取所选数据库alias；不存在admin则委托官方createsuperuser交互，已有有效超级管理员则委托changepassword，其他admin拒绝重置/提权。密码不接收命令行/环境值、不写日志，不在迁移或启动时改密。不同数据库独立初始化，QA隔离凭据不作Owner密码源。

前端复用shadcn Sheet/Button和原统一API错误/CSRF。显式.machine-form-footer同时约束button与asChild链接，等宽Grid/44px最小高度、窄屏堆叠；赛事Grid共享六列、名称左对齐/其他列居中、长文案可换行。只对明确操作区应用规则，保留图标按钮规格。真实截图和36组页面布局矩阵见[UAT报告](project/UAT-FIX-01-verification.md)，不将DOM测试冒充像素检查。

Owner后续追加全站下拉整改：统一components/ui/select.tsx基于既有Radix Select，触发器46px、菜单项至少44px；Portal/Popper负责弹层、视口避让和Sheet层级，应用主题变量统一视觉，长文案换行、限制高度并滚动。九处业务入口全部复用，空字符串和数字ID只在组件/调用边界转换，API不变；保留Radix不可交互的aria-hidden表单桥接。新增交互测试及真实展开证据见[下拉清单](project/UAT-FIX-01-select-inventory.md)与UAT报告追加节。
