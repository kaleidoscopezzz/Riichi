# Riichi 架构与F0-06兼容设计

状态：F0-05正式CLOSED / PASS；当前D0-01仅修订文档，F0-06未启动。已实现事实与未来设计在下文分开说明。业务详细规则只在[F0-06功能规范](F0-06-functional-spec.md)维护，范围见[requirements](requirements.md)。

## 技术与模块（当前事实）

前后端分离、模块化单体。Python3.13/Django5.2 LTS/DRF、React/TypeScript/Vite、Tailwind/shadcn/ui/Lucide；SQLite开发，PostgreSQL仅预留驱动/配置。PostgreSQL实连并发与生产部署仍UNVERIFIED，不因已有锁代码或文档方案改为已验证。

| 目录/模块 | 当前职责 |
| --- | --- |
| backend/config | base/local/production设置、URL、WSGI/ASGI；环境变量与安全配置 |
| backend/common | 匿名GET /api/v1/health/、统一JSON错误和API中间件 |
| backend/accounts | AbstractUser、官方密码校验、原子注册/档案创建、Session/CSRF |
| backend/players | PlayerProfile、一对一身份边界、本人昵称、管理员搜索分页 |
| backend/machines | 物理设备台账、capacity_slot四台容量、状态/退役、共同设备池锁 |
| backend/tournaments | Tournament/Participant及首轮Round/Table/Seat/Allocation；规则配置与冻结、分配历史 |
| frontend/src/layouts、pages、components、services、styles | 布局路由、页面交互、shadcn基础组件、统一Cookie/CSRF请求、Riichi Premium主题 |
| docs/project | 基线制度及F0-01～05原始报告/证据，历史快照不可改写 |

当前主要页面为/dashboard、/tournaments、/tournaments/:id/rounds、/players、/machines、/profile、/settings和公开/login、/register。分桌工作台仅首轮与轮次级设备管理，没有成绩/累计榜/冠军页面。

开发由Vite同源/api代理到Django。认证使用HttpOnly Session Cookie，前端写请求初始化当前CSRF，凭据不写localStorage或日志；注册/登录/退出显式csrf_protect，DRF写请求沿用SessionAuthentication校验。全部管理接口在服务端IsAdminUser，健康接口匿名。

成功响应为data，失败为error(code/message/fields)，健康接口保持原有独立契约。健康只表示存活，不代表生产数据库就绪。配置来自.env/环境变量，来源显式限定，无全局CORS；正式环境必须独立密钥、HTTPS与安全Cookie。

## F0-05现有实体和事务（当前事实）

| 实体 | 已实现关系与约束 |
| --- | --- |
| User / PlayerProfile | AbstractUser在accounts/0001_initial；OneToOne档案，用户名和昵称分别保存 |
| MahjongMachine | 稳定id、三位machine_no、名称/位置/说明、四种基本状态；capacity_slot唯一且非退役必须占1～4槽 |
| Tournament | 数字规则、Uma JSON十进制字符串、draft/started、创建者与时间、内部revision；尚无策略版本或completed |
| TournamentParticipant | User业务档案FK、(tournament,player)唯一、启动昵称快照 |
| TournamentRound | Tournament FK；(tournament,round_number)唯一、CHECK 1～6；服务仅允许生成1 |
| RoundTable | Round FK、每轮table_number 1～4唯一，是轮次逻辑桌，不是赛事级稳定A～D桌位 |
| RoundSeat | Round/Table/Participant FK；每桌四风唯一、每人每轮唯一；跨表归属由clean/服务审计 |
| MachineAllocation | RoundTable与稳定machineId FK PROTECT；active machine/table条件唯一；released具有释放时间/管理员、保留编号快照 |

当前MahjongMachine的available/maintenance/disabled均占四台容量，retired只读释放容量。新增设备服务仍依次尝试四个槽；只改文档或数据库约束并不能消除服务代码的四台限制。

Tournament草稿编辑与启动先条件UPDATE父行revision，事务内校验数字配置/名单、写昵称快照与started_at；started规则和名单不可编辑。Uma只做精确字符串校验，Oka用Decimal推导，没有实际半庄计分。

当前首轮SystemRandom.shuffle一次，四人一组四风，按机器编号升序从available且无active分配的池选择，全轮原子写入。资源不足/重复生成拒绝，不覆盖已有RoundTable/RoundSeat。后续轮次明确返回不可执行；设备释放不改变Tournament.started，也不代表成绩确认。

当前设备状态变更、生成、调整、释放共用machines.locking.lock_machine_pool：SQLite先无值变化UPDATE取得写预留，PostgreSQL按稳定PK顺序锁物理池；之后生成再锁赛事/写子记录。条件唯一约束额外防双占；跨表四人完整性不是数据库CHECK。内存/文件SQLite历史验证见原报告；PostgreSQL未实测。

## F0-06目标架构（设计建议，尚未实现）

核心仍留在tournaments模块，新增职责清晰的成绩、规则策略、累计/排名、完赛与抽签服务；无需微服务、任务队列或动态公式引擎。物理资源从“每轮分配中心”简化为“赛事选桌与占用”，正常轮次只重排选手和四风。

| 建议实体/扩展 | 职责与约束方向 |
| --- | --- |
| Tournament新增规则/完赛字段 | score_tie_policy、champion_tiebreak_policy、rules_version及赋值来源；目标completed/完成时间/冠军引用，启动冻结与完赛快照 |
| TournamentTable（赛事稳定逻辑桌） | Tournament FK、ordinal 1～4/显示A～D唯一；不复用某轮RoundTable主键充当全赛事桌位 |
| TournamentMachineReservation（赛事预留） | 稳定逻辑桌与machineId、active/released、预留/释放/替换审计；active machine与active赛事桌位分别唯一 |
| RoundTable扩展 | 可空FK连接赛事稳定桌位及生成时映射/预留版本，保留现有id/table_number；历史和当前替换映射分别展示 |
| TableResult / SeatResult（命名待实现确认） | 每桌一份当前成绩与四人条目，draft/confirmed、版本、有符号整数终局点数（含负数/零）、共享名次、无损有理数结果和规则快照、录入/确认审计；唯一约束防重复 |
| LotteryRecord / FinalStanding（命名待实现确认） | 公开抽签组/过程/完整顺序及管理员确认；完赛最终排序、唯一冠军、规则/结果版本快照 |

新模式需显式选桌、确认A～D映射，选桌数量为人数/4，可用且无他场预留；新首轮与预留原子落库。后续每轮RoundTable引用同一赛事桌位，不释放预留再抢设备。故障替换新建预留历史版本，后续沿用新设备，不改旧轮次映射快照或座次。

MachineAllocation保留原表、FK和历史，不把旧记录伪装成赛事级预留。新模式以赛事Reservation为资源权威；新轮次通过赛事桌位/预留映射查询当前设备，不能为每轮复制相互冲突的active MachineAllocation，也不能捏造released记录表示从未发生的释放。序列化明确返回resource_mode与reservation来源，原历史allocation查询保持可追溯，不能拿预留ID冒充旧allocation ID。

策略注册表按冻结标识/版本计算，不执行用户表达式；每场仅支持已批准预设。TBD-001/002均RESOLVED，详细公式和决胜链只见[统一规范](F0-06-functional-spec.md)。后端采用Fraction等精确有理数完成计分、累计和排名；Decimal/字符串可精确解析输入，不能先经float或有限精度除法再转换。数据库无损保存整数分子/正整数分母或等价精确表示及规则版本；展示近似值不参与比较，不以SQLite NUMERIC或字符串字典序代替精确排序。

正式确认须验证四个终局点数均为整数（允许负数和零）且总和等于4×赛事开局点数；异常可保存草稿，不能绕过确认校验。后续分桌依次比较已确认累计积分、第一名次数、第二名次数、从最近已确认轮向前的逐轮积分，完全相同使用首轮持久化随机序列。旧首轮序列从既有逻辑桌号及东南西北顺序无损还原，不能以记录ID替代或重新随机；新轮四风另行随机并持久化。冠军全同仍公开抽签，禁止使用首轮分桌兜底。

累计从已确认结果派生，可重建的缓存不作为真相源；下一轮保存来源结果版本，前轮未全确认、源版本变化或重复轮次均拒绝。最终结果在明确完赛事务保存，不随策略升级静默重算；公开抽签必须显式确认，不能后台静默决定冠军。

### 事务与权限目标

资源相关操作统一“物理桌稳定PK顺序→赛事→赛事桌位/预留→结果或最终快照”的锁顺序，沿用当前简单池锁亦可，不能因店内超过四张便引入复杂调度系统。SQLite须先取得写事务；PostgreSQL有序行锁加条件唯一约束，实际行为另测，不声称方案已通过。

成绩草稿/确认和下一轮生成共同保护赛事及结果版本；不需要资源锁的纯成绩事务不能在持有反序锁后再调用会拿资源锁的完赛逻辑。建议正式完赛作为独立明确操作：重新校验全部轮次、确认成绩、决胜/抽签、唯一冠军，原子保存最终结果并释放仅属于本赛事的预留及需结束的旧active分配。失败全部回滚，不能先完赛后异步释放。

新模式禁止用旧单轮release绕过赛事预留；保留故障替换的明确审计接口，日常不要求人工释放。旧模式接口须与Reservation同事务协调，不能在新旧两套表各自独立判断空闲。所有新API继续管理员Session、CSRF、严格字段和统一错误，不允许客户端提交权威积分或冠军。

## 兼容与迁移（设计建议，尚未执行）

本D0-01只写方案。下面是F0-06在同一任务内实施、在真实F0-05副本上验证的新增迁移/服务升级步骤，不是后续独立功能阶段。

1. **预检与备份**：覆盖F0-04已启动未分桌及F0-05已生成分桌两类赛事，记录库版本、迁移图、machineId/轮桌座/分配行数及关联。检测重复active、跨表异常、缺失快照、部分释放等情况，出具问题清单，不删数据修平。上线升级期间暂停旧资源写入，避免旧进程绕过新预留表。
2. **先扩展结构**：新增规则标识/版本及来源字段、赛事桌位/Reservation、结果/抽签/最终快照结构；RoundTable仅新增可空关联。保留所有旧主键、原数字参数、外键、0001/0002迁移、现有桌号/四风及历史审计。
3. **回填规则版本**：为旧赛事赋split_rank_bonus_v1/performance_v1/rules_version=1，记录legacy_default_backfill和迁移来源，不伪造历史管理员选择。赋值不修改已冻结数字规则或生成座次，不声称此前已有成绩/冠军。
4. **桥接旧占用**：以现存active MachineAllocation建立一一可追溯Reservation镜像/legacy引用，数据库active machine唯一，新旧占用统一互斥；released旧记录只保留历史，不重新变active。旧轮table_number对应赛事A～D桌位，保留原RoundTable/RoundSeat，并明确映射继承自旧记录，不伪造历史手动选桌。按首轮已保存桌号升序及每桌东南西北还原原始随机序列，记录来源/完整性校验，不以ID排列替代、不重排首轮。
5. **按最终决策接续**：F0-04已启动未分桌赛事经新流程选桌后生成首轮并持久化随机序列；F0-05已有首轮保持不变。原占用全部有效、数量与桌次完整且无跨赛事冲突时，直接继承固定桌位，不额外要求人工采纳。部分/全部已释放或其他异常占用必须管理员复核，显示旧座次及历史；需要后续实体对局时确认当前可用固定映射，不得自动抢回已被他场占用的旧桌。若不再需要后续实体对局，复核后处理历史成绩及正常完赛，只释放本场仍有效预留，不为补记录临时占新桌。需复核的记录未处理前不得自动接续或虚构完赛。
6. **解除容量依赖**：新增迁移移除machine_active_capacity_slot这一“非退役必须占1～4槽”CHECK；capacity_slot可暂留为nullable只读legacy列，原1～4值保留，唯一约束即使保留也不能要求新设备非空。同步改造create_machine四槽重试及界面容量逻辑，新设备不再分槽；继续保留状态、编号唯一、稳定machineId和退役历史保护。不得只改前端或让新服务仍卡在四槽算法。本阶段不实际执行此迁移。
7. **切换资源权威**：新建赛事默认固定选桌模式；旧记录有清晰legacy_round_v1来源/兼容状态。所有旧调整/释放及新预留/替换/完赛共用锁和Reservation权威，跨模式独占。设备维护/停用/退役保护同时检查赛事预留和未桥接的旧active记录，不能因新轮次不创建旧allocation便误判为空闲。旧模式仍可审计原释放记录；继承或复核确认固定映射后，旧单轮release不能释放赛事预留。需要结束的旧active行只能在真实替换/完赛等经确认操作中写合法释放审计，不能迁移时篡改其历史状态。
8. **验证后收紧**：核对前后ID、旧字段、行数/关系、编号快照、分桌哈希及首轮随机序列；验证新增非空字段/唯一约束，仅有问题的记录进入管理员复核。新旧模式查询完整，旧历史始终可读。保留备份及失败证据；不通过删除新旧表或重放随机结果解决失败。

赛事规则冻结与资源兼容接续分别审计：接续物理桌不是修改开局点数/Uma/名单。故障替换时旧轮次可查询生成时物理桌及替换历史，当前桌位显示新预留；不能只显示最新设备让过去历史失真。

### 回归与部署风险

必须覆盖“F0-04已启动未分桌、F0-05全有效占用直接继承、部分released、全released、改编号/退役/编号复用、被另一赛事占用”等副本场景，验证新旧资源互斥和首轮序列不变。Planner已允许修改与新需求冲突的旧测试断言，例如四台上限或后续轮次拒绝；须逐项记录规则差异并补新需求回归，保留全部仍有效的旧测试及历史验收证据，不能删除失败用例冒充回归。

物理池扩大后的锁范围、有理数无损存储/比较、数据回填及事务重入须在F0-06实测。PostgreSQL迁移/并发、真实部署/HTTPS和公网安全目前均未验证。五项最终决策由[统一规范决策表](F0-06-functional-spec.md#13-planner最终决策与启动门禁)维护，已不再是业务开放问题；具体字段/API名称仍为实现设计，不冒充已经完成。

## 审查与开发门禁

D0-01仅修改Markdown，保存历史事实；F0-06完整范围和验收见统一规范。Planner批准、Owner推送文档Commit、远程内容核验一致之前不得编码或迁移。F0-06之后仅集成测试、部署、安全加固与发布验收，微信/团体赛仍不纳入V1.0。
