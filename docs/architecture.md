# Riichi 架构与 F0-06 兼容实现

状态：F0-01～F0-05、D0-01保持原正式验收记录。PR #1 Docker生产部署、PR #2审查修复及CI已合并，生产任务起点main为`34d4cbdea89bba81a503f2b476f2e1d69de5d714`；F0-06历史Tag不改判。业务规则以[统一功能规范](F0-06-functional-spec.md)为准；历史[F0-06交付](project/F0-06-verification.md)、[Docker验证](project/docker-production-verification.md)与[本轮生产验证](project/production-launch-verification.md)分别对应各自候选和环境。

## 技术与模块（当前实现）

前后端分离、模块化单体。Python 3.13 / Django 5.2 LTS / DRF；React / TypeScript / Vite / Tailwind / shadcn/ui / Lucide；SQLite开发，PostgreSQL生产。生产在既有Docker/Nginx/Gunicorn/PostgreSQL基础上增加Caddy；不引入Redis、Celery或微服务。

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

## 生产入口与代理信任

```text
浏览器 → Caddy :80/:443（HTTP跳转、Let's Encrypt、续期）
                   ↓ 内部proxy网络，仅HTTP
               Nginx :8080（React静态资源、API代理、登录限流）
                   ↓ 内部web网络
               Gunicorn / Django
                   ↓ 内部data网络
               PostgreSQL → postgres_data持久卷
```

只有Caddy发布宿主机端口并接入可出网的edge网络；proxy、web、data均为内部网络，Nginx不接data，数据库不接proxy/web。Nginx的8081只供容器健康探针。Caddy的`/data`及`/config`分别用命名卷持久化证书、ACME账户和状态，更新镜像不清卷；不得将卷内私钥放进Git或公开日志。真实域名、来源、密钥、数据库凭据仅存在部署机的私有`.env`。

Caddy作为直接公网边缘，不信任客户端自带的代理头；向Nginx传递规范化的HTTPS来源和客户端IP。内部proxy子网与Caddy固定地址可配置，部署前检查与宿主机/现有Docker网络无冲突。Nginx只信任该精确Caddy地址：以原始TCP对端校验入口，再解析真实客户端地址，用规范化来源重写传给Django的`X-Forwarded-Proto`、`X-Forwarded-For`、`X-Real-IP`和Host。登录限流按验证后的客户端IP计数，不能按Caddy地址合并所有用户，也不能让公网头绕过限流。

API不发布端口，仅在该受控拓扑启用`TRUST_PROXY_HEADERS`。Django保留HTTPS重定向、Secure/HttpOnly Session、Secure CSRF、明确主机/HTTPS来源，不启用全局CORS。Caddy不得经Host或客户端代理头选择不受控上游；非法Host、直接内部入口及伪造代理头在网络/代理层拒绝或覆盖。接入CDN或其他前置代理属于新的信任边界变更，须单独设计验证，不能扩大为信任任意私网或公网来源。

公开health仍是liveness；容器API readiness还核对数据库连接与待迁移。首次建库、更新迁移、管理员初始化不在容器启动中自动执行。维护入口在升级期间返回受控503，备份/恢复/回滚按[生产操作手册](deployment-linux.md)执行；真实CA与续期证据见[本轮报告](project/production-launch-verification.md)，QA内部CA不替代生产验收。

## 领域与持久化

| 实体 | 实现和约束 |
| --- | --- |
| MahjongMachine | 原ID/编号/状态/历史保留；capacity_slot为nullable只读legacy列，旧值及唯一索引保留，新设备NULL；现役三位编号唯一、状态/名称CHECK仍有效 |
| Tournament | draft/started/completed，数字规则/Uma字符串、两个策略ID/rules_version/rules_source；revision、首轮序列/来源、资源兼容状态/审计、冠军FK、完成管理员/时间及final_snapshot |
| TournamentParticipant | 关联PlayerProfile；赛事内player唯一、启动时昵称快照；nullable eliminated_after_round标记参赛资格，1～5轮范围CHECK，历史关系保留 |
| TournamentTable | 全赛事稳定逻辑桌ordinal 1～4/A～D；赛事内ordinal唯一，范围CHECK |
| TournamentMachineReservation | active/released、稳定machineId、编号快照、操作者/时间/原因、可空OneToOne legacy_allocation；active逻辑桌条件唯一、释放审计CHECK，跨赛事机器可共享，赛事内不重复由服务校验 |
| TournamentRound | 1～6且赛事轮号唯一；generation_snapshot保存规则、来源成绩版本、排序输入、首轮顺序引用 |
| RoundTable | 保留原ID/table_number，新增可空TournamentTable FK和生成时machine_snapshot；故障替换不改旧快照 |
| RoundSeat | 原Round/Table/Participant FK、桌内四风唯一、轮内选手唯一；全员及跨FK归属由服务验证 |
| MachineAllocation | 原轮次级表和全部FK/历史保留，原active条件唯一及release审计CHECK保留；新轮不复制active旧分配 |
| TableResult | 每桌OneToOne；draft/confirmed、version、points JSON（participant ID→有符号整数/空值）、scores、规则快照、录入/确认管理员及时间；确认状态CHECK |
| LotteryRecord | 赛事、来源成绩版本与资格、purpose/淘汰轮次、组员、完整顺序、方式/过程/实际抽签时间、记录/确认管理员与时间；用途/轮次CHECK |
| EliminationRecord | 每轮OneToOne、四个稳定participant ID、原来源成绩/资格、确认时排名快照、抽签引用、确认人/时间，所有FK PROTECT |

成绩请求只引用本桌既有participant ID，不接受换座、权威积分或冠军字段。草稿允许缺项/空值；确认及更正必须四人整数、总和4×开局且版本匹配。原始点数范围为±(2^53−1)，保证JSON到浏览器均为精确整数；超范围明确400，不截断。赛事进行中已确认成绩通过显式更正接口更新并留档，完赛后只读。默认未存成绩version=0，首次成功写入为1，之后成功写入递增。

2026-11-07更正扩展新增TableResultCorrection（FK TableResult/User均PROTECT）：递增前后版本、完整before/after JSON快照、操作者/时间和可选说明；同表唯一约束与连续版本CHECK保护审计链，跨表对应及前后值由服务保证。correct_result沿用物理池→赛事→子记录锁顺序，在同一事务校验CAS、更新该桌精确分数和确认信息、插入更正记录；失败整体回滚。旧轮次、座次、映射和后续已确认结果保持原数据。

新增`POST /api/v1/round-tables/{id}/result/preview/`只读试算、`POST .../correct/`保存更正、`GET .../corrections/`查询历史，均为管理员Session且POST正确校验CSRF。普通保存/确认接口继续拒绝覆盖已确认成绩；未确认历史轮次不再限定为最后一轮。试算复用点数白名单及Fraction计分，部分输入的奖励/积分为空值，异常合计不强制修正；合计/差额以字符串返回以免JSON溢出安全整数。前端150ms请求、取消及输入标识保护响应，显式保存才改变正式成绩。

所有权威奖励、基础分、累计和比较采用Fraction，从整数或精确Uma/Oka十进制字符串构造。JSON和数据库保存规范化`{"numerator":"50","denominator":"3"}`，分子/正分母均为字符串，不经float或有限精度舍入。仅支持`split_rank_bonus_v1` / `performance_v1`，规则版本1沿用自动推导Oka，版本2增加独立的可选头名赏配置；未知版本拒绝计算，不执行动态表达式。

Tournament新增nullable `oka_override`（最多64字符的非负十进制字符串，NULL为自动推导，`"0"`为无头名赏），`oka`属性/API字段仍只读并返回实际生效值。新增写字段复用草稿父行锁、revision检查及启动冻结；自定义值不修改starting_points/return_points。新建默认版本2、`created_v2`来源；旧草稿明确自定义时升级版本并记录`draft_configured_v2`，普通读取、启动或其他字段编辑不自动升级，版本1和自定义字段并存的请求被拒绝。版本2快照同时保存`oka_override`和实际`oka`，版本1快照保持原结构。

累计来自当前已确认结果；metric按总分、第一次数、第二次数、逆序单场积分比较，更正后查询自动采用新分数。后续分桌才追加首轮持久化顺序，组内重新随机四风，已生成轮次保留原generation_snapshot。最终完全同分各组必须公开抽签、保存后另行确认；不能以ID/首轮顺序暗定名次。抽签仅在完整source_versions及并列组匹配时用于排名，过期记录保留；完赛final_snapshot仅引用排名实际使用的lottery_id，并冻结全体结果、唯一冠军、规则和来源版本，读取不重算历史。

工作台单次读取将已确认TableResult与TournamentParticipant分别加载为同批对象；排行榜、统计、当前抽签适用性、淘汰预览、source_versions及participant_statuses均由这些对象派生，不在计算排行后另读新版本或资格。并发更正/淘汰发生在读取途中时，显示内容及来源仍一致，晚到淘汰审计不叠加到旧资格榜单。随后写事务拒绝过期来源，避免管理员批准旧榜单却保存另一份排名。该读取不写库、不取得赛事写锁；生成/更正/淘汰/完赛仍共享原有写锁。

## 事务与共享桌关联

所有新写入统一使用**物理池稳定PK→赛事revision写锁→子记录**。SQLite先no-op UPDATE取得写事务；PostgreSQL先事务advisory锁再按PK select_for_update。成绩也用同一顺序，避免确认/生成/完赛反序死锁。保留唯一/CHECK兜底，跨表归属、四人完整性和单赛事不重复选机属于服务事务检查，不冒称普通CHECK能跨FK保证。

新Reservation表示赛事与设备关联，选桌不检查其他赛事的关联或旧active分配，只使用已锁池中的真实available机器。新首轮必须提交恰好初始人数/4个不重复machine_ids，按管理员预览顺序映射A～D，关联/序列/轮桌座原子提交。后续不再选桌、释放或复制active旧分配。`occupied_ids`仅供旧轮次分配兼容路径使用，保留MachineAllocation原active机器唯一约束；新关联不阻止设备维护/停用/退役，旧真实active Allocation保护仍保留。生成下一轮重检实际使用桌的状态，需换桌时明确拒绝。

故障替换要求可用且未被本赛事其他逻辑桌重复关联的目标及原因，结束本场旧关联、建立新关联；其他赛事的关联不受影响。有legacy引用时只在真实替换/完赛写本场旧释放审计。旧单轮释放/调整接口发现赛事固定桌位即409拒绝，不能绕过预留约束。资源GET返回每个设备的完整reservations数组及status派生assignable，旧singular reservation字段仅作兼容。所有旧历史GET接口继续可读；ID空间不混用。

下一轮须连续、上一轮每桌全部确认且全员完整，重复/跳轮/草稿返回409；保存生成输入后原子写轮次/座次。完赛重新检查所有配置轮次、全部已确认成绩、来源版本、抽签及唯一冠军；同一事务保存completed/快照并仅释放本场预留及需结束的本场旧active。失败整体回滚；网络失败或409不会自动重放写请求。

## 兼容与迁移（已实现，QA验证）

1. 开发前只读检查Owner库迁移图及SHA256，SQLite backup到忽略目录；不迁移Owner库。所有验证在独立QA库及副本。
2. 新增machines/0003仅移除machine_active_capacity_slot容量CHECK，保留旧列/值/主键。create_machine同步移除四槽循环，UI移除四台上限。原0001/0002不改。
3. 新增tournaments/0003扩展字段及实体，保留原始轮桌座/分配表。0004回填`legacy_default_backfill:0004`规则来源及迁移时间，不修改任何旧列（包含updated_at）、数字配置、名单或座次。
4. F0-04已启动无首轮保持unselected，按新选桌流程接续。F0-05按旧桌号及东南西北恢复first_round_order，order_source=legacy_table_wind_v1，不重抽也不用记录ID。
5. 原active全部有效时建立稳定A～D及OneToOne legacy Reservation桥接，resource_state=fixed，直接继承。桥接的created_at表示升级接入时间，source/legacy FK及原分配时间明确可追溯，不伪造历史手动选桌。
6. 部分/全部released、机器异常或结构不完整标review_required，不恢复released、不自动抢回旧桌；仍有效的active保留可追溯桥接。管理员显式说明并补选可用映射；全部配置轮次已存在且无需实体对局可确认historical_only，补历史成绩后正常完赛，不临时关联物理桌。
7. 源码升级期间必须停止旧进程写入；数据库不能以跨表普通CHECK阻止旧二进制直接写表。旧MachineAllocation保留自身约束，新关联按最新共享策略，旧接口对固定桌保护保持。
8. 带数据QA比较所有旧列、数量、稳定ID/关系/座次/历史，验证有效继承、partial/released复核及当前关联规则。原始日志及迁移失败/修复证据见交付报告。0004不可逆，回退须停写并按部署备份方案处理，不fake/删库。

2026-11-06 Oka配置扩展新增`tournaments/0007_configurable_oka`：增加nullable字段、仅调整新对象的规则版本/来源默认值，并增加自定义Oka非负格式及版本2的同表CHECK。没有数据回填，不修改任何既有版本、规则来源、时间戳、配置或结果/完赛快照；0001～0006保持原文。隔离迁移演练比较全部旧列和关系，并覆盖草稿、进行中、已完赛及20/19.996/0/−20的旧推导结果，实测范围见[本次验证](project/configurable-oka-verification.md)。实际业务库/生产库升级仍须先备份、独立恢复核对，再按迁移计划操作。

成绩更正新增`0008_result_corrections`，仅创建审计表，不回填虚构更正，也不改任何旧列或历史迁移。带数据QA比对已确认/完赛结果、规则/座次/抽签、旧分配及预留，备份和独立恢复升级见[更正验证](project/score-corrections-verification.md)。业务库本轮未迁移。

## 新赛事分桌预设与桌附加基础分

新建可选标识为`random_v1`、`ranked_v1`、`manual_v1`，默认高高碰，创建/草稿选择后启动冻结。既有`swiss_repeats_first_v1`、`swiss_scores_first_v1`继续执行，创建/其他草稿切换被服务端拒绝；既有瑞士草稿可保持原值，前端用明确历史标签。`legacy_v1`仅赋给原有赛事，配套`table_bonus_policy=none`及各桌零值，旧原点数/规则版本/来源/结果/座次/完赛快照不变。

`pairing.py`瑞士分组用4人组合及子集DP，锚定最低剩余种子位置以消除桌位排列重复；以公共分母缩放Fraction积分后比较整数成本。两项成本为组内历史相遇次数总和、组内6对积分绝对差总和，按优先级词典序最小化；相同成本用种子位置序列稳定决定。不同重遇对数只是另一个展示统计，不能替代算法主成本。4人不可避重会明确显示，16人搜索有运行回归。

`POST /api/v1/tournaments/{id}/rounds/preview/`只读获取冻结名单/当前确认结果同批次及历史座次，生成签名计划。计划绑定当前管理员、赛事、轮数、revision、完整source_versions、规则及首轮随机序列，30分钟有效；生成端原子核对，旧计划/错误身份/过期/篡改均拒绝。原自动生成调用仍可直接使用冻结策略，手动模式必须提交预览及完整4人分组，固定物理桌/资源锁沿用原顺序。

PairingBoard用PointerEvents手柄交换，桌位人数始终4人；触屏在Sheet实际滚动容器边缘用RAF滚动并重新命中目标，取消/失去capture/忙碌/卸载清理。键盘通过统一Radix Select交换。初始与重新预览统一请求路径，含目标轮次/重试标识与Abort/current保护，迟到响应不覆盖新计划。

`ranked_table_bonuses`为A～D四项非负精确十进制字符串，独立计分策略标识`add_table_base_bonus_v1`。首轮和非高高碰桌均0；高高碰后续轮桌的`base_bonus`及来源在生成时固定。基础积分增加该值，同桌四人均增加，原Uma/Oka算法版本1/2不重新解释，原始总点数要求不变。每桌规则快照保存该附加分，试算/确认/更正/累计/冠军使用同一值；已生成分组和附加分不随前轮更正改写。

新增0009仅扩展字段/约束，旧行赋legacy/none/0并核对原字段投影，新对象默认值与旧行值区分；不伪造旧管理员选择，不修改0001～0008。008历史演练现在固定在008目标，009有单独带数据演练。[实际验证](project/pairing-strategies-verification.md)区分本机QA与生产/CI未验证范围。

## 可选淘汰、资格来源与统计

`EliminationRecord`通过OneToOne绑定已有轮次，每轮一次；`TournamentParticipant.eliminated_after_round`仅影响后续资格，初始关系、User、昵称及首轮序列保持。结构校验在轮r接受NULL或淘汰轮次≥r的参赛者，所以旧轮继续完整合法，新轮使用active子集。固定桌A～D不删除，实际生成仅使用A～active人数/4；多余桌的关联在淘汰事务内留痕结束，设备可供本赛事故障替换，多余桌状态不参与新轮门禁。任一释放失败也回滚淘汰审计及四人资格。

`elimination_preview`读取同批已确认成绩与资格，要求当前及全部此前轮次成绩完整，比较原完整metric，只对跨越末四人边界的完全并列组要求公开抽签。`confirm_elimination`在原锁内重验当前轮、全部成绩、剩余赛程/至少四人、同批来源及四人名单，原子记录审计和四人资格；新淘汰来源不得为空且须完整匹配服务端状态，审计写服务端同批canonical来源，不套用旧完赛来源兼容。下一轮已生成即拒绝。`placement_metric`在原积分metric前增加资格阶段，仍在赛者在前、淘汰较晚者在前，各阶段原比较规则保留；更正不自动恢复资格。

LotteryRecord新增`purpose`与可空`elimination_round`，CHECK约束二者组合；跨赛事归属仍由服务验证。淘汰用途只服务当前轮边界，最终用途只服务全部轮次结束的同阶段并列；二者分别匹配完整成绩与资格来源，保持待确认唯一、作废审计及确认后不可作废。分桌签名也增加完整participant_statuses，首轮完整序列仍保留，groups只覆盖当前active成员。

`performance_stats.py`从确认scores或既有完赛快照的rounds派生显示统计，使用Fraction计算四位回避率，全体并列领先者返回ID数组。无逐轮数据的旧最简快照不补造统计；读取只深拷贝并添加展示字段，不保存或重算权威积分。前端用BigInt格式化两位小数/百分比，逐轮基础、顺位奖励与积分分开展示，精确值可展开。

0010只新增淘汰记录、资格及抽签作用域列/约束，移除新Reservation的全局机器唯一索引，逻辑桌唯一和释放审计保持；旧行资格NULL、抽签用途final，不虚构淘汰或改旧策略。0001～0009原迁移不变，0009历史演练固定在0009；本轮带数据备份/独立恢复与原字段投影核对见[赛事流程验证](project/event-flow-verification.md)。真实业务库本轮未迁移。

## 新增麻将机自动编号

新增设备表单只填写名称、位置、状态及备注，编号由服务端分配，编辑时只读。`machine_no`为现有三位业务编号，`id`仍为稳定身份，两者不改类型或历史值，不新增模型/迁移。创建API省略machine_no时从001～999选择最小未被非退役设备占用的编号；旧接口显式编号及归一化仍兼容。沿用原退役号可复用规则，复用时为全新设备ID，旧分配/昵称等历史引用不改。编号用完返回明确409，不覆盖任何设备。

create_machine也加入原有物理池锁顺序；SQLite空池先无操作DML获得写预留，PostgreSQL在池PK行锁前取得数据库内事务级advisory锁，解决空表无法由行锁串行化的自动分号竞争。所有创建/状态/分配路径保持同一锁顺序，提交或回滚释放锁，不依赖Redis或全局服务。实际验证见[自动编号报告](project/machine-auto-number-verification.md)。

## 历史边界与验证限制

F0-05当时是最多四台、轮次级自动选机、仅首轮、无成绩/冠军；原报告/失败证据与历史Tag保留。旧自动生成器仅在`legacy_test_fixture.py`供历史数据回归构造，运行时路由/服务不引用；正常入口只接受显式选桌。与新需求冲突的旧断言已逐项更新并补回归，有效旧权限/数据约束/历史测试继续执行。

文件SQLite并发、故障回滚、真实HTTP及16人6轮浏览器闭环的实际结果以对应交付报告为准。PR #1报告已记录Linux ARM64容器PostgreSQL及自签HTTPS的隔离验证；本轮候选、真实域名CA、浏览器及生产服务器另见本轮验证报告，不将旧测试或有序锁设计当成生产验证通过。F0-06后仅集成测试、部署、安全加固、发布验收；微信/团体赛不属V1.0。

## UAT-FIX-01 账号与选手维护兼容

不新增实体或迁移。PlayerProfile仍OneToOne User，信号仍原子建档；新选手由players/services.py生成唯一player_UUID用户名、set_unusable_password并明确非staff/superuser，昵称单独保存。既有普通User/档案不强制重建或改密码，但登录接口禁止非staff，后台API（含me/个人资料）要求IsAdminUser，公开注册端点在CSRF校验后固定403。管理员自身档案保留，仅用于后台显示资料，不作为新参赛候选。

玩家列表/详情返回id/nickname/is_active/reference_count/can_delete/创建更新时间，不含内部用户名/密码。昵称搜索和active/archived筛选、page分页，eligible=true始终排除归档与管理员。编辑、归档、恢复先User写预留/锁，再Profile锁，匹配赛事名单校验User→Profile顺序；SQLite首个写语句在读取状态前取得写事务。

删除先查任意TournamentParticipant引用，有引用409且不写历史；无引用只删业务Profile并停用User，保留用户级审计，不做User级联删除。归档使用User.is_active=False，新赛事选人与启动校验拒绝；不改已启动冻结名单/昵称、RoundSeat、成绩、排行榜或冠军。管理员档案CRUD返回受保护冲突，不会误归档/删除系统管理员。

init_admin仅在Owner明确命令调用时读取所选数据库alias；不存在admin则委托官方createsuperuser交互，已有有效超级管理员则委托changepassword，其他admin拒绝重置/提权。密码不接收命令行/环境值、不写日志，不在迁移或启动时改密。不同数据库独立初始化，QA隔离凭据不作Owner密码源。

前端复用shadcn Sheet/Button和原统一API错误/CSRF。显式.machine-form-footer同时约束button与asChild链接，等宽Grid/44px最小高度、窄屏堆叠；赛事Grid共享六列、名称左对齐/其他列居中、长文案可换行。只对明确操作区应用规则，保留图标按钮规格。真实截图和36组页面布局矩阵见[UAT报告](project/UAT-FIX-01-verification.md)，不将DOM测试冒充像素检查。

Owner后续追加全站下拉整改：统一components/ui/select.tsx基于既有Radix Select，触发器46px、菜单项至少44px；Portal/Popper负责弹层、视口避让和Sheet层级，应用主题变量统一视觉，长文案换行、限制高度并滚动。九处业务入口全部复用，空字符串和数字ID只在组件/调用边界转换，API不变；保留Radix不可交互的aria-hidden表单桥接。新增交互测试及真实展开证据见[下拉清单](project/UAT-FIX-01-select-inventory.md)与UAT报告追加节。

## 审查问题修复（fix/review-findings）

新增迁移tournaments/0005（LotteryRecord.voided_by/voided_at/void_reason及`lottery_void_state` CHECK：未作废三字段为空；作废须有人、时间、非空原因且未确认）与0006（TournamentMachineReservation.release_reason；已释放旧行复制原reason，旧列不改，reverse为noop）。均只加字段，旧列与旧迁移不变。

- 抽签：record_lottery在赛事锁内拒绝同组、同来源版本的第二条待确认记录（`lottery_pending`）；void_lottery同序加锁、留痕作废，已确认不可作废，完赛后只读。排名与完赛只引用已确认记录。
- 成绩：只确认不带点数时以update_fields保存，草稿录入人/时间不变。
- 预留：reason为建立原因，release_reason为释放原因，mapping.history同时返回。
- 兼容：bridge_legacy与0004使用同一判定，畸形首轮不抛错而进入review_required，仍桥接active分配；historical_only赛事禁止故障换桌；复核缺逻辑桌返回409。
- 赛事草稿：输出只读revision，写入可选revision，比较在首条条件UPDATE内完成。
- 认证与错误：非staff登录与密码错误同为400；DRF使用common.authentication.CsrfSessionAuthentication，CSRF失败统一`csrf_failed`；Http404为`not_found`；ApiErrorMiddleware替换错误体时保留原响应头与Cookie。
- 输入：common.api.validate_display_name拒绝控制字符与文字方向控制符；search_text拒绝列表搜索中的控制字符。

前端新增lib/points.ts（统一点数解析）、lib/redirect.ts（站内回跳）、lib/field-errors.ts（嵌套错误展开）与components/error-boundary.tsx。CI见`.github/workflows/ci.yml`。详细证据见[修复报告](project/review-findings-fix-verification.md)。
