# Riichi 开发约束

## 当前任务与规范

Owner于2026-11-10授权团队赛规划后进一步明确“实现功能并测试通过”（分支`codex/team-tournaments`），入口为[团队赛规划](docs/team-tournament-plan.md)。已确认可配置队伍/成员、每桌各队一人、自由场次与固定位置循环、精确团队积分求和和不自动调整分桌场数；另确认建议默认：自由赛程各队等场，同队不同人可并发，可兼任位置和下周期换人，同周期同位置一人打满场数；团队总分→第一合计→第二合计→公开抽签；启动冻结成员，首版不加团队淘汰/桌附加分/个人奖。授权本轮代码及隔离QA迁移/测试，不授权写Owner库或部署正式服务器；个人赛既有规则/历史保持，实际验证另记团队赛交付报告。

Owner于2026-11-10追加赛事流程要求（分支`codex/event-flow`）：排行榜与逐轮明细优先展示小数积分，保留精确值入口，增加四位回避率、单个半庄最高终局点数及当桌第一次数的真实统计。不同赛事允许同时关联同一可用麻将机，单赛事仍不得重复选同桌，维护/停用设备不可选。每轮结束、下一轮生成前，管理员可选择预览并确认淘汰累计排名末四人；每轮最多淘汰四人，始终保留至少四人打完剩余配置轮次。淘汰保留原参赛关系与审计；跨越淘汰边界的完全并列用公开抽签，后续更正不自动复活已淘汰选手或改动已生成座次。新赛事不再提供瑞士轮选项，既存瑞士赛事保留冻结策略与历史。此项覆盖下述历史跨赛事占桌互斥、全轮完整初始名单和新建瑞士轮限制；其他计分与冠军规则不变。实际验证见[赛事流程验证](docs/project/event-flow-verification.md)。

Riichi定位为**轻量级四人立直麻将个人赛事管理系统**，帮助管理员快速组织比赛、录入成绩、重排座次并决出冠军；设备调度不是产品主线。需求以[requirements](docs/requirements.md)为总览，F0-06详细规则以[统一功能规范](docs/F0-06-functional-spec.md)为准，技术与兼容设计见[architecture](docs/architecture.md)。

Owner本轮追加分桌扩展：新赛事创建/草稿选择手动、完全随机、高高碰或瑞士轮两种优先级，启动固定；手动每轮生成前拖拽排人，高高碰后续轮次各桌四人可固定加基础积分，首轮随机不加桌附加分。瑞士轮按累计历史相遇次数和精确积分差总和进行双目标优化，优先级可选；生成前预览、生成后保留。旧赛事标legacy_v1，原字段/成绩不重算。本项覆盖旧“仅固定后续分桌、不避重、不附加积分”的范围限制，禁止任意公式/动态表达式仍有效。当前分支codex/pairing-strategies，验证见[分桌扩展](docs/project/pairing-strategies-verification.md)。

Owner于2026-11-07追加授权：赛事进行中允许更正任意已有轮次的成绩，包括第二轮开始后的第一轮；编辑数字时实时展示积分。当前追加工作分支`codex/score-corrections`，基线main `06feff5`。更正保存前后完整快照及操作者/时间，说明可选；已生成轮次保留座次，累计排名和未生成轮次按新成绩处理，旧抽签按来源版本保留为历史；完赛后仍只读。实际验证见[成绩更正验证](docs/project/score-corrections-verification.md)。此项覆盖下述历史“确认后只读”限制，既有计分/冠军策略和历史验收证据保持不变。

当前任务 **Linux生产上线第一阶段：Caddy工程与集成交付（分支 `codex/production-launch`）**。只读核验的起点为本地及远程 main `34d4cbdea89bba81a503f2b476f2e1d69de5d714`，工作区当时干净；PR #1 Docker生产部署和PR #2审查问题修复/CI均已合并。Owner最新范围要求：完成工程、测试、Push/PR、CI全绿、独立审查、合并main后停止；第二阶段等待Owner提供新服务器并明确授权，第一阶段绝不连接旧服务器或任何正式服务器。任务计划与进度见[生产上线计划](docs/project/production-launch-plan.md)，本轮实际命令、证据、阻塞与UNVERIFIED见[生产上线验证](docs/project/production-launch-verification.md)。旧修复分支、未提交等描述是历史阶段快照，不代表当前Git状态。

本轮保留Docker、Nginx静态资源/API代理/登录限流，增加Caddy为唯一公网80/443入口，自动申请/续期Let's Encrypt并持久化ACME状态；校验Caddy→Nginx→Django的HTTPS、代理头及真实客户端IP信任。生产IP/域名仅为忽略的运行参数，不写入仓库配置、测试或通用文档。默认沿用服务器现有业务库，缺库时正常初始化空库；不导入本地Owner SQLite。完整赛事写入只在隔离QA，生产只做管理员登录、读取与安全检查，不造业务记录。

F0-01～F0-05保持CLOSED / PASS，D0-01文档Commit `5f31891b4ae3a589057e7054758abb08ca42ec72`。F0-05正式代码基线解引用为`41929da1e53f8bb481beb4ea3bc31b65f9ee86ff`。远端另有Tag `baseline/F0-06`（2026-11-04 14:09创建，解引用`b9e83bb0c8e31ab660b37e7e0a46c1f0bb424e65`，说明为“approved”，早于UAT-FIX-01整改）与`checkpoint/UAT-FIX-01`（解引用`c9d7bb87d4c8badb33513a38a147c9a24807c924`）。该Tag与“UAT再次验收后才建立F0-06基线”的旧表述不一致，其最终含义由Owner确认，文档不据此自行改判验收状态。所有历史迁移/报告/证据与Tag保留。

V1.0当前只供雀庄老板/管理员使用。公开注册关闭，普通用户不可登录或进入任何后台页面；选手不需要本人注册/登录。管理员维护PlayerProfile，新增选手沿用内部唯一User、set_unusable_password、无staff/superuser权限；管理员自身自动档案不进入选手列表或新赛事有效名单。归档以User.is_active管理，历史参赛关系和昵称快照不改。

## 技术与工程边界

- 前后端分离、模块化单体：backend为Python3.13/Django5.2 LTS/DRF，SQLite开发、PostgreSQL生产；frontend为React/TypeScript/Vite/Tailwind/shadcn/ui/Lucide。生产为Caddy→Nginx→Gunicorn/Django→PostgreSQL，只有Caddy发布公网端口。
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
- 已合并的审查修复新增tournaments/0005（LotteryRecord作废人/时间/原因及状态CHECK）与0006（Reservation.release_reason；已释放旧行复制原reason到新列，旧列不改）。生产库升级前盘点、停写、一致备份并在独立恢复库演练，核对实际迁移图和计划；不得修改这两份或更早历史迁移，不fake、不清库。本地Owner库保持不写。

- 已解除四台现役上限，capacity_slot仅保留nullable legacy列和旧值，新设备NULL；单赛事显式选1～4张真实物理桌，A～D固定贯穿轮次，故障替换审计，完赛自动释放。
- Tournament为draft/started/completed；启动冻结数字规则、策略/版本、名单和昵称。TableResult为每桌OneToOne，草稿版本、整数原始点数、确认审计及无损有理数结果；进行中已确认成绩经显式更正入口及版本校验可修改，前后值留档，完赛后只读。
- 新赛事用TournamentTable/Reservation；保留MachineAllocation和轮桌座全部历史及稳定ID。所有资源写入检查新预留与旧active记录，并共用物理池PK→赛事→子记录锁顺序。
- 新增迁移回填可追溯规则来源、旧首轮序列及预留桥接，不改旧列（含updated_at）、旧迁移、原始座次或历史分配状态。原占用有效完整则继承，released/异常需复核，不自动抢回旧设备。
- 全部配置轮次已存在、无需后续实体对局的旧赛事，可复核为historical_only后补历史成绩和正常完赛，不临时占新桌。已释放旧记录不恢复active。
- Owner开发库只读核验与备份；开发验证仅在忽略目录中的独立QA库及副本。PR #1历史报告已验证Linux ARM64容器PostgreSQL；该结果不替代本轮代码和真实服务器验证，实际状态按本轮报告逐项记录。跨表完整性由服务校验，不冒称CHECK保证。

## 已确认计分及冠军规则

- TBD-001 **RESOLVED**：`split_rank_bonus_v1`，终局原始同点均分覆盖名次的Uma及第一名Oka，禁止座次/ID隐藏优先；公式、示例和条件零和见统一规范。
- TBD-002 **RESOLVED**：`performance_v1`，总分→第一次数→第二次数→从最后轮向前的单场积分→公开抽签，管理员确认/审计，冠军唯一。同一并列组同时仅允许一条待确认抽签记录；录入有误须填写原因作废（保留记录及作废人/时间/原因）后重录，已确认记录不可作废。
- Fraction等精确有理数完成权威计分、累计、排名及无损存储；Decimal/字符串可精确解析输入，禁止先经float或有限精度舍入。前端近似展示不参与排序，禁止浮点累计。实现见tournaments/scoring.py。
- 每场独立保存策略标识、rules_version及数字配置，草稿可改支持项、启动冻结；历史赋可追溯默认版本，不改原配置/分桌，不静默重算历史。
- 终局点数允许负数/零，四人均须整数；正式确认总和必须等于4×开局，异常可存草稿但无跳过校验入口。
- 后续分桌依次按累计分、第一名次数、第二名次数、逆序逐轮积分排序，完全相同按首轮持久化随机排列顺序；新轮四风重新随机。旧首轮序列从已有桌号/东南西北还原，不用记录ID或重新抽序；该兜底不用于冠军决胜。
- Planner五项最终决策已确认，规范OP-01～OP-05均RESOLVED。除Owner本轮明确批准的分桌预设与固定桌附加分外，不添加罚分、任意积分补正、座次轮换或其他赛制；已发布历史不重算。

## 验证与交付

UAT交付继续回归F0-06完整4人1轮、8/12人多轮、16人6轮，覆盖负数/零/总和校验、有理数无损精度、成绩锁定、后续分桌与首轮兜底、冠军全同公开抽签、固定选桌/自动释放、旧数据兼容、并发/回滚、管理员/Session/CSRF及真实API/UI。Planner允许修改与新需求冲突的旧断言，但须记录差异、保留原有效测试和历史验收证据，并补新需求回归；不得删失败用例或篡改证据冒充通过。

功能开发交付须实际执行Django check/migrate/makemigrations检查/全量测试、TypeScript/Vitest/build/npm audit、HTTP/浏览器/安全忽略检查，保存准确命令、环境、结果及UNVERIFIED。历史测试结果不能冒充本轮实际执行。F0-06后的历史范围为集成测试、部署、安全加固、发布验收；Owner本轮团队赛实现授权覆盖该历史候选限制，微信及未授权扩展仍为未来候选。团队赛实际结果见[团队赛验证](docs/project/team-tournaments-verification.md)。

仓库 CI 在 main、`codex/**` 分支推送和 PR 时运行双库后端全量测试、前端检查、ShellCheck、Compose 校验、启动器 PS5.1 静态检查及 Linux Docker/Chromium 隔离 QA。真实 Windows 首次安装和正式服务器验收单独记录。

## Git与停止限制

- 第一阶段Owner已明确授权在最新main派生的独立任务分支开发、更新文档、自检、提交、推送、创建PR、独立审查并在测试/CI全部通过后合并main；合并后停止。第二阶段等待Owner提供新服务器并明确授权，当前不得连接任何正式服务器、部署、迁移生产库或初始化生产管理员。不得直接在main开发、强推、重写历史、删除旧Tag/证据、绕过失败CI或分支保护；不自动创建历史验收Tag。
- 独立Reviewer审查最终候选，开发自检不替代独立结论；GitHub强制独立账号审批而当前身份无法满足时才请求Owner处理。旧阶段“Owner负责Git/开发者停止”仅约束对应历史任务，不覆盖本轮授权。
- 第二阶段获准后先盘点真实服务器服务、端口、卷、数据库、磁盘和防火墙，遇非本项目服务冲突或无法验证数据保护时停止受影响部署，不抢占资源。使用已配置SSH认证；不提取或要求粘贴私钥。未知主机密钥须由可信渠道核对，不关闭StrictHostKeyChecking。
- 生产数据库按备份、独立恢复核对、明确迁移计划后部署；不覆盖现有.env、不轮换已有密钥/密码、不逆迁移。新管理员沿用交互init_admin，由Owner输入密码；已有管理员不重复初始化或改密。真实域名证书/浏览器/服务器未实测项不得标PASS。
- 第一阶段报告记录GitHub PR/CI、独立审查、合并SHA、QA备份恢复和未验证项；实际部署SHA与线上验收留待第二阶段，不得预填。历史[审查问题修复报告](docs/project/review-findings-fix-verification.md)、验收结论与失败证据原文保留，后续事实采用追加追记。

## Windows启动器与README

- README只放产品介绍、真实界面、简洁启动与文档入口，禁止本机绝对路径、账号密码、历史工作日志及虚构部署/许可证/CI/覆盖率。品牌与图片存仓库、相对引用。
- 启动器逻辑在scripts，bat只作入口；根目录从脚本位置推导，兼容Windows PowerShell5.1、中文/空格路径，无管理员要求，无全局安装。PowerShell脚本UTF-8 BOM、bat CRLF。
- 沿用环境及本地设置；缺少配置可经确认生成随机本地密钥，禁止覆盖已有.env或默认管理员密码。迁移前只读核对真实库与迁移图，必须明确确认后正常migrate；验证仅在隔离副本/QA库进行。
- 仅管理启动器创建的进程树。使用Windows Job Object收束子进程，停止前校验目录/运行ID/命令行/PID/创建时间/可执行路径，并在同一内核句柄复验；严禁按python.exe/node.exe名称终止。端口占用拒绝抢占；PID不存在或创建时间不同即证明原进程已退出（state中记录的子进程同样按PID+创建时间核对），只清理本项目过期状态，绝不终止该PID上的进程；创建时间相同但可执行路径/命令行不符或无法读取属于身份歧义，拒绝并要求人工核对。状态、日志、临时文件与依赖缓存留在忽略目录。
- 交付须保存真实Windows首次/重复/停止、中文空格、缺工具/端口/服务/迁移/DB故障及PID复用测试证据，保留失败记录；完整Django与前端回归、源码范围/密钥/忽略/diff检查。未实测的平台或部署标UNVERIFIED。
