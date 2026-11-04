# Riichi 开发约束

## 当前任务与规范

Riichi定位为**轻量级四人立直麻将个人赛事管理系统**，帮助管理员快速组织比赛、录入成绩、重排座次并决出冠军；设备调度不是产品主线。需求以[requirements](docs/requirements.md)为总览，F0-06详细规则以[统一功能规范](docs/F0-06-functional-spec.md)为准，技术与兼容设计见[architecture](docs/architecture.md)。

当前任务 **F0-06：完整赛事运行、精确计分与冠军决出**，已获Owner/Planner正式授权。D0-01已CLOSED / PASS，文档Commit为`5f31891b4ae3a589057e7054758abb08ca42ec72`；Owner确认已推送及双端核验。开发起点main/HEAD已核对，F0-05代码基线Tag解引用为`41929da1e53f8bb481beb4ea3bc31b65f9ee86ff`。

F0-01～F0-05均已正式CLOSED / PASS。F0-06是V1.0最后一次核心功能开发，本次交付为未提交候选，须等待Planner独立验收，不得自行标正式CLOSED或建立基线。完整范围不拆F0-07/F0-08，不继续下一阶段。

## 技术与工程边界

- 前后端分离、模块化单体：backend为Python3.13/Django5.2 LTS/DRF，SQLite开发、PostgreSQL生产预留；frontend为React/TypeScript/Vite/Tailwind/shadcn/ui/Lucide。
- 配置、公共服务、accounts、players、machines、tournaments按现有边界组织，不引入微服务、Redis、Celery、任意公式编辑器或动态表达式执行。
- 运行时、虚拟环境、依赖和缓存留在项目内；不得全局安装或改全局环境。稳定依赖锁随真正依赖变更维护；F0-06未新增依赖。
- 简体中文、Riichi Premium、统一组件和反馈，桌面/手机、深浅主题、键盘与焦点、可读对比度。只展示真实API数据，不虚构赛事、选手、成绩或统计。
- 密钥、DEBUG、主机、数据库及来源走环境变量；不提交.env、数据库、依赖、构建和凭据，不开放全局CORS，不把开发配置当生产配置。
- 先读相关实现再做授权范围修改，不擅改产品范围。技术设计选择不能改变已确认业务规则；新的业务分歧须另报Planner。

## 身份、会话及历史保护

- AbstractUser在accounts/0001_initial，PlayerProfile通过OneToOne关联AUTH_USER_MODEL；原子注册/档案创建，不新建平行身份体系。
- 沿用Django SessionAuthentication。注册/登录/退出显式csrf_protect，DRF写操作正确CSRF；前端Cookie凭据、写前取当前CSRF，仅请求内存保留，不写localStorage或日志。
- 管理员仅createsuperuser初始化，无默认管理员密码。服务端权限/严格字段白名单，普通用户只改本人资料，不在前端独立决定权限。
- 改迁移前查迁移图及真实库，先备份副本验证；禁止修改历史迁移、fake、删库、清数据或重建掩盖兼容异常。生产数据库未验证必须标UNVERIFIED。
- machineId、TournamentParticipant、RoundTable、RoundSeat及MachineAllocation历史身份保持稳定，不用编号或昵称关联历史。

## 当前实现与兼容保护

- 已解除四台现役上限，capacity_slot仅保留nullable legacy列和旧值，新设备NULL；单赛事显式选1～4张真实物理桌，A～D固定贯穿轮次，故障替换审计，完赛自动释放。
- Tournament为draft/started/completed；启动冻结数字规则、策略/版本、名单和昵称。TableResult为每桌OneToOne，草稿版本、整数原始点数、确认审计及无损有理数结果；确认后只读。
- 新赛事用TournamentTable/Reservation；保留MachineAllocation和轮桌座全部历史及稳定ID。所有资源写入检查新预留与旧active记录，并共用物理池PK→赛事→子记录锁顺序。
- 新增迁移回填可追溯规则来源、旧首轮序列及预留桥接，不改旧列（含updated_at）、旧迁移、原始座次或历史分配状态。原占用有效完整则继承，released/异常需复核，不自动抢回旧设备。
- 全部配置轮次已存在、无需后续实体对局的旧赛事，可复核为historical_only后补历史成绩和正常完赛，不临时占新桌。已释放旧记录不恢复active。
- Owner开发库只读核验与备份；验证仅在忽略目录中的独立QA库及副本。PostgreSQL仍UNVERIFIED；跨表完整性由服务校验，不冒称CHECK保证。

## 已确认计分及冠军规则

- TBD-001 **RESOLVED**：`split_rank_bonus_v1`，终局原始同点均分覆盖名次的Uma及第一名Oka，禁止座次/ID隐藏优先；公式、示例和条件零和见统一规范。
- TBD-002 **RESOLVED**：`performance_v1`，总分→第一次数→第二次数→从最后轮向前的单场积分→公开抽签，管理员确认/审计，冠军唯一。
- Fraction等精确有理数完成权威计分、累计、排名及无损存储；Decimal/字符串可精确解析输入，禁止先经float或有限精度舍入。前端近似展示不参与排序，禁止浮点累计。实现见tournaments/scoring.py。
- 每场独立保存策略标识、rules_version及数字配置，草稿可改支持项、启动冻结；历史赋可追溯默认版本，不改原配置/分桌，不静默重算历史。
- 终局点数允许负数/零，四人均须整数；正式确认总和必须等于4×开局，异常可存草稿但无跳过校验入口。
- 后续分桌依次按累计分、第一名次数、第二名次数、逆序逐轮积分排序，完全相同按首轮持久化随机排列顺序；新轮四风重新随机。旧首轮序列从已有桌号/东南西北还原，不用记录ID或重新抽序；该兜底不用于冠军决胜。
- Planner五项最终决策已确认，规范OP-01～OP-05均RESOLVED。不得重新引入互斥方案，或添加罚分、积分补正、座次轮换、避重对手等其他赛制。

## 验证与交付

F0-06交付须验证完整4人1轮、8/12人多轮、16人6轮，覆盖负数/零/总和校验、有理数无损精度、成绩锁定、后续分桌与首轮兜底、冠军全同公开抽签、固定选桌/自动释放、旧数据兼容、并发/回滚、管理员/Session/CSRF及真实API/UI。Planner允许修改与新需求冲突的旧断言，但须记录差异、保留原有效测试和历史验收证据，并补新需求回归；不得删失败用例或篡改证据冒充通过。

功能开发交付须实际执行Django check/migrate/makemigrations检查/全量测试、TypeScript/Vitest/build/npm audit、HTTP/浏览器/安全忽略检查，保存准确命令、环境、结果及UNVERIFIED。历史测试结果不能冒充本轮实际执行。F0-06之后仅集成测试、部署、安全加固、发布验收；微信、团体赛仍属未来候选。

## Git与停止限制

- 保持main，F0-06不执行git commit、tag、push，不改远端、历史或已有基线，不删除文件。
- Owner负责Git提交/推送/Tag，Planner负责独立源码验收及双端核验。自检不替代外部验收。
- F0-06报告须列文件/API契约、模型/迁移兼容、计分/冠军、真实HTTP/UI闭环、自动化/文件SQLite并发/回滚、旧断言变更、失败证据、UNVERIFIED和Git状态；完成停止，等待Planner。
