# Riichi 开发约束

## 当前任务与规范

Riichi定位为**轻量级四人立直麻将个人赛事管理系统**，帮助管理员快速组织比赛、录入成绩、重排座次并决出冠军；设备调度不是产品主线。需求以[requirements](docs/requirements.md)为总览，F0-06详细规则以[统一功能规范](docs/F0-06-functional-spec.md)为准，技术与兼容设计见[architecture](docs/architecture.md)。

当前任务 **审查问题修复（本地分支 `fix/review-findings`）**。起点为main `b882ef065bbd9ebae55f6a04ea324675ee41e3fb`（已合并PR #1 Docker生产部署），工作区干净。范围是代码审查发现的问题：公开抽签同组仅一条待确认记录及留痕作废、成绩录入与确认审计分离、旧赛事兼容边界、登录/错误码/错误响应头、昵称与搜索输入校验、赛事草稿乐观并发、前端登录回跳/抽签刷新/点数严格解析/错误边界、Windows启动器PID复用自愈与PS5.1探测、部署跳转端口与备份目录，并新增CI。新增迁移tournaments/0005、0006（只加字段；0006仅把已释放预留的旧reason复制到新列，不改旧列）。验证使用独立QA数据库，不写Owner数据库；Owner库升级前须备份并明确确认迁移。

F0-01～F0-05保持CLOSED / PASS，D0-01文档Commit `5f31891b4ae3a589057e7054758abb08ca42ec72`。F0-05正式代码基线解引用为`41929da1e53f8bb481beb4ea3bc31b65f9ee86ff`。远端另有Tag `baseline/F0-06`（2026-11-04 14:09创建，解引用`b9e83bb0c8e31ab660b37e7e0a46c1f0bb424e65`，说明为“approved”，早于UAT-FIX-01整改）与`checkpoint/UAT-FIX-01`（解引用`c9d7bb87d4c8badb33513a38a147c9a24807c924`）。该Tag与“UAT再次验收后才建立F0-06基线”的旧表述不一致，其最终含义由Owner确认，文档不据此自行改判验收状态。所有历史迁移/报告/证据与Tag保留。

V1.0当前只供雀庄老板/管理员使用。公开注册关闭，普通用户不可登录或进入任何后台页面；选手不需要本人注册/登录。管理员维护PlayerProfile，新增选手沿用内部唯一User、set_unusable_password、无staff/superuser权限；管理员自身自动档案不进入选手列表或新赛事有效名单。归档以User.is_active管理，历史参赛关系和昵称快照不改。

## 技术与工程边界

- 前后端分离、模块化单体：backend为Python3.13/Django5.2 LTS/DRF，SQLite开发、PostgreSQL生产预留；frontend为React/TypeScript/Vite/Tailwind/shadcn/ui/Lucide。
- 配置、公共服务、accounts、players、machines、tournaments按现有边界组织，不引入微服务、Redis、Celery、任意公式编辑器或动态表达式执行。
- 运行时、虚拟环境、依赖和缓存留在项目内；不得全局安装或改全局环境。稳定依赖锁随真正依赖变更维护；F0-06未新增依赖。
- 简体中文、Riichi Premium、统一组件和反馈，桌面/手机、深浅主题、键盘与焦点、可读对比度。只展示真实API数据，不虚构赛事、选手、成绩或统计。
- 全站单选业务下拉复用components/ui/select.tsx（Radix Select + Portal/Popper），禁止新增可交互的原生select或页面私有菜单；参赛名单多选联想统一使用components/player-picker.tsx（Radix Popover + Portal，combobox/listbox语义），按player_id去重，复用eligible分页API，保留取消/乱序/IME保护；保持空值、禁用、严格校验与API参数，交互测试及深浅主题展开截图随UI变更验证。Radix内部aria-hidden表单桥接不属于原生业务菜单，不得为扫描结果删除其表单语义。
- 密钥、DEBUG、主机、数据库及来源走环境变量；不提交.env、数据库、依赖、构建和凭据，不开放全局CORS，不把开发配置当生产配置。
- 先读相关实现再做授权范围修改，不擅改产品范围。技术设计选择不能改变已确认业务规则；新的业务分歧须另报Planner。

## 身份、会话及历史保护

- AbstractUser在accounts/0001_initial，PlayerProfile通过OneToOne关联AUTH_USER_MODEL；沿用原子内部User/档案创建，不新建平行身份体系；公开注册403。
- 沿用Django SessionAuthentication。关闭的注册端点及登录/退出仍显式csrf_protect，DRF写操作正确CSRF；前端Cookie凭据、写前取当前CSRF，仅请求内存保留，不写localStorage或日志。
- 管理员通过init_admin委托Django交互初始化/改密，无默认密码。已有admin非有效超级管理员时拒绝提权或重置；Owner自己输入密码，不从旧QA credentials.json读取，不在迁移/启动时自动改密。服务端权限/严格字段白名单，普通用户不可进入后台；管理员资料仅维护本人显示名称，不在前端独立决定权限。
- 改迁移前查迁移图及真实库，先备份副本验证；禁止修改历史迁移、fake、删库、清数据或重建掩盖兼容异常。生产数据库未验证必须标UNVERIFIED。
- machineId、TournamentParticipant、RoundTable、RoundSeat及MachineAllocation历史身份保持稳定，不用编号或昵称关联历史。

## 当前实现与兼容保护

- 未被赛事引用的PlayerProfile可确认物理删除，同时仅停用内部User以保留身份审计；不级联删除User。被任意草稿/历史赛事引用须归档，必要时恢复。User→Profile锁顺序与赛事参赛校验一致，管理员档案禁止普通选手CRUD。
- UAT-FIX-01未新增迁移，不改变Owner库或实际admin密码，所有QA独立库。按钮修复只作用于显式操作区，桌面六列统一Grid、赛事名左对齐，其余居中；320/390px卡片和换行不溢出。
- 审查修复轮新增tournaments/0005（LotteryRecord作废人/时间/原因及状态CHECK）与0006（Reservation.release_reason；已释放旧行复制原reason到新列，旧列不改）。Owner库升级前须备份、只读核对迁移图后明确确认；验证只在QA库及副本。

- 已解除四台现役上限，capacity_slot仅保留nullable legacy列和旧值，新设备NULL；单赛事显式选1～4张真实物理桌，A～D固定贯穿轮次，故障替换审计，完赛自动释放。
- Tournament为draft/started/completed；启动冻结数字规则、策略/版本、名单和昵称。TableResult为每桌OneToOne，草稿版本、整数原始点数、确认审计及无损有理数结果；确认后只读。
- 新赛事用TournamentTable/Reservation；保留MachineAllocation和轮桌座全部历史及稳定ID。所有资源写入检查新预留与旧active记录，并共用物理池PK→赛事→子记录锁顺序。
- 新增迁移回填可追溯规则来源、旧首轮序列及预留桥接，不改旧列（含updated_at）、旧迁移、原始座次或历史分配状态。原占用有效完整则继承，released/异常需复核，不自动抢回旧设备。
- 全部配置轮次已存在、无需后续实体对局的旧赛事，可复核为historical_only后补历史成绩和正常完赛，不临时占新桌。已释放旧记录不恢复active。
- Owner开发库只读核验与备份；验证仅在忽略目录中的独立QA库及副本。PostgreSQL仍UNVERIFIED；跨表完整性由服务校验，不冒称CHECK保证。

## 已确认计分及冠军规则

- TBD-001 **RESOLVED**：`split_rank_bonus_v1`，终局原始同点均分覆盖名次的Uma及第一名Oka，禁止座次/ID隐藏优先；公式、示例和条件零和见统一规范。
- TBD-002 **RESOLVED**：`performance_v1`，总分→第一次数→第二次数→从最后轮向前的单场积分→公开抽签，管理员确认/审计，冠军唯一。同一并列组同时仅允许一条待确认抽签记录；录入有误须填写原因作废（保留记录及作废人/时间/原因）后重录，已确认记录不可作废。
- Fraction等精确有理数完成权威计分、累计、排名及无损存储；Decimal/字符串可精确解析输入，禁止先经float或有限精度舍入。前端近似展示不参与排序，禁止浮点累计。实现见tournaments/scoring.py。
- 每场独立保存策略标识、rules_version及数字配置，草稿可改支持项、启动冻结；历史赋可追溯默认版本，不改原配置/分桌，不静默重算历史。
- 终局点数允许负数/零，四人均须整数；正式确认总和必须等于4×开局，异常可存草稿但无跳过校验入口。
- 后续分桌依次按累计分、第一名次数、第二名次数、逆序逐轮积分排序，完全相同按首轮持久化随机排列顺序；新轮四风重新随机。旧首轮序列从已有桌号/东南西北还原，不用记录ID或重新抽序；该兜底不用于冠军决胜。
- Planner五项最终决策已确认，规范OP-01～OP-05均RESOLVED。不得重新引入互斥方案，或添加罚分、积分补正、座次轮换、避重对手等其他赛制。

## 验证与交付

UAT交付继续回归F0-06完整4人1轮、8/12人多轮、16人6轮，覆盖负数/零/总和校验、有理数无损精度、成绩锁定、后续分桌与首轮兜底、冠军全同公开抽签、固定选桌/自动释放、旧数据兼容、并发/回滚、管理员/Session/CSRF及真实API/UI。Planner允许修改与新需求冲突的旧断言，但须记录差异、保留原有效测试和历史验收证据，并补新需求回归；不得删失败用例或篡改证据冒充通过。

功能开发交付须实际执行Django check/migrate/makemigrations检查/全量测试、TypeScript/Vitest/build/npm audit、HTTP/浏览器/安全忽略检查，保存准确命令、环境、结果及UNVERIFIED。历史测试结果不能冒充本轮实际执行。F0-06之后仅集成测试、部署、安全加固、发布验收；微信、团体赛仍属未来候选。

仓库CI（.github/workflows/ci.yml）在push main及PR时运行SQLite与PostgreSQL后端check/makemigrations/migrate/全量测试、前端typecheck/Vitest/build/npm audit、部署脚本ShellCheck与Compose校验、启动器PS5.1解析与BOM检查。CI通过不替代真实Windows首次安装、浏览器及生产部署验证；README不得引用未实际运行的CI结果。

## Git与停止限制

- 当前任务在本地分支fix/review-findings，不执行git commit、tag、push或merge，不改远端、历史、既有基线与验收证据。
- Owner负责Git提交/推送/Tag，Planner负责独立源码验收及双端核验。自检不替代外部验收。
- 本轮修复报告见[审查问题修复报告](docs/project/review-findings-fix-verification.md)，列修改文件、逐项修复与测试、迁移验证、Django/前端回归、UNVERIFIED和Git状态；完成停止，等待Owner验收。保留历史报告和证据。

## Windows启动器与README

- README只放产品介绍、真实界面、简洁启动与文档入口，禁止本机绝对路径、账号密码、历史工作日志及虚构部署/许可证/CI/覆盖率。品牌与图片存仓库、相对引用。
- 启动器逻辑在scripts，bat只作入口；根目录从脚本位置推导，兼容Windows PowerShell5.1、中文/空格路径，无管理员要求，无全局安装。PowerShell脚本UTF-8 BOM、bat CRLF。
- 沿用环境及本地设置；缺少配置可经确认生成随机本地密钥，禁止覆盖已有.env或默认管理员密码。迁移前只读核对真实库与迁移图，必须明确确认后正常migrate；验证仅在隔离副本/QA库进行。
- 仅管理启动器创建的进程树。使用Windows Job Object收束子进程，停止前校验目录/运行ID/命令行/PID/创建时间/可执行路径，并在同一内核句柄复验；严禁按python.exe/node.exe名称终止。端口占用拒绝抢占；PID不存在或创建时间不同即证明原进程已退出（state中记录的子进程同样按PID+创建时间核对），只清理本项目过期状态，绝不终止该PID上的进程；创建时间相同但可执行路径/命令行不符或无法读取属于身份歧义，拒绝并要求人工核对。状态、日志、临时文件与依赖缓存留在忽略目录。
- 交付须保存真实Windows首次/重复/停止、中文空格、缺工具/端口/服务/迁移/DB故障及PID复用测试证据，保留失败记录；完整Django与前端回归、源码范围/密钥/忽略/diff检查。未实测的平台或部署标UNVERIFIED。
