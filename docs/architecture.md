# 工程架构

## 技术与边界

Riichi 使用前后端分离、模块化单体。浏览器运行 React 应用，通过版本化 HTTP JSON API 访问 Django/DRF；开发环境数据库为 SQLite，正式环境预留 PostgreSQL。

| 层 | 技术 | 职责 |
| --- | --- | --- |
| Web | React、TypeScript、Vite | 路由、布局、页面状态和 API 交互 |
| UI | Tailwind CSS、shadcn/ui、Lucide React | Riichi Premium 设计变量、基础组件与图标 |
| API | Python 3.13、Django 5.2 LTS、DRF | 版本化接口、配置及公共服务 |
| 存储 | SQLite / PostgreSQL | 本地开发 / 正式环境预留 |

当前提供健康检查、账号/选手档案、设备台账、Tournament配置/冻结，以及F0-05首轮随机分桌和物理设备分配/释放历史。成绩、后续轮次、计分与冠军判定未实现。

## 顶层目录

```text
Riichi/
├── backend/              Django 配置、公共服务、测试与依赖锁
├── frontend/             React 应用、基础组件、API 服务与构建配置
├── docs/
│   ├── requirements.md   已确认范围和 TBD
│   ├── roadmap.md        分阶段路线
│   ├── architecture.md   架构与组织
│   └── project/
│       └── baselines.md  双基线制度与状态
├── AGENTS.md             开发和交付约束
├── README.md             安装、启动、验证
├── .gitignore            环境、密钥和生成文件忽略规则
└── .gitattributes        文本换行约定
```

项目内 `.tools/`、虚拟环境与依赖缓存是本机运行资源，不纳入版本管理。

## 后端组织

```text
backend/
├── config/
│   ├── settings/         base.py / local.py / production.py
│   ├── urls.py           API 路由入口
│   ├── asgi.py / wsgi.py 服务入口
│   └── tests.py          配置安全约束测试
├── common/
│   ├── apps.py           公共能力应用
│   ├── urls.py / views.py 健康检查
│   └── tests.py          API 与 CORS 测试
├── manage.py
├── requirements.in       直接依赖约束
├── requirements.txt      完整精确依赖锁
└── .env.example          无真实密钥的示例
```

Django 项目配置负责 URL、WSGI/ASGI 与设置组织；公共服务模块负责 health 接口与其测试。`base` 共享配置，`local` 本地配置，`production` 强制生产安全条件。环境变量管理 `SECRET_KEY`、`DEBUG`、`ALLOWED_HOSTS`、数据库和跨域来源；本地示例密钥留空，缺少有效随机密钥会启动失败，生产环境必须提供独立安全值。

健康接口契约：

```http
GET /api/v1/health/
Content-Type: application/json
```

```json
{"status":"ok","service":"riichi-api","api_version":"v1"}
```

该接口表示 API 进程可响应，不代表生产数据库、业务流程或所有外部服务已就绪。接口不要求注册登录，不返回环境密钥、连接串或调试信息。

## 前端组织与请求流

```text
frontend/
├── src/
│   ├── layouts/app-layout.tsx   导航、Header、面包屑与内容容器
│   ├── pages/                  仪表盘、统一业务占位、设置和未找到页面
│   ├── components/             主题、导航及健康状态组件
│   │   └── ui/                 shadcn/ui 基础组件
│   ├── services/health.ts      健康请求与响应契约校验
│   ├── styles/globals.css      主题变量和全局样式
│   ├── lib/utils.ts            通用样式合并工具
│   ├── app.tsx                 路由定义
│   └── main.tsx                React 入口
├── public/                     静态资源
├── components.json             shadcn/ui 生成与别名配置
├── vite.config.ts              构建和本地 API 代理
├── package.json / package-lock.json
└── .env.example
```

布局层统一导航、Header、面包屑和内容容器；页面层组合仪表盘、业务空状态与基础系统信息；`components` 承载通用组件，`services` 封装健康请求，`styles` 管理主题和全局规则。健康状态与主题各自的 Context/Hook 独立于 Provider 组件文件，保持 React 热更新边界稳定。

| 路由 | 页面 |
| --- | --- |
| `/` | 跳转 `/dashboard` |
| `/dashboard` | 仪表盘 |
| `/tournaments` | 管理员赛事列表、创建/编辑草稿、详情与启动确认 |
| `/tournaments/:id/rounds` | 管理员首轮分桌工作台、资源池、调整/释放与历史 |
| `/players` | 管理员分页查询、搜索已注册选手 |
| `/machines` | 管理员设备资源台账、编辑与退役 |
| `/settings` | 系统设置与基础信息 |
| `/profile` | 本人选手档案与昵称修改 |
| `/login` / `/register` | 公开登录与注册 |
| 其他路径 | 未找到页面 |

开发时，浏览器访问本地 Vite，`/api` 由 Vite 代理到 `http://127.0.0.1:8000`。Django 的直接跨域访问仅允许明确配置的本地 React 来源，禁止通配放行。生产需由部署环境提供前端静态资源与 API 转发/来源配置，Vite 开发服务器不作为生产服务。

健康请求显示加载、成功或失败状态，并支持重试。仪表盘不以虚构数据填充统计卡片。业务占位说明功能边界，不能呈现已创建赛事或已注册选手的假象。

## Riichi Premium

基础为深海军蓝、石墨黑和中性色，使用适度金色或青绿色强调。统一 Typography、Spacing、Radius、Border、Shadow 与 Hover，通过主题变量管理。默认暗色并预留亮色切换；桌面采用侧栏布局，窄屏保证导航和主内容可访问。避免无意义渐变、过量动画和装饰性统计图。

## 后续扩展原则

账号、选手、设备、赛事、分桌和成绩能力按任务逐步落地；领域规则放在各App服务内，不进入公共health。Tournament独立持久化，微信仍属未来规划，不引入空模块。

## F0-04 Tournament 与冻结事务

`tournaments/` 按 models、rules、serializers、services、views、urls、tests 和 migrations 分工。Tournament以FK PROTECT引用创建者User；TournamentParticipant以FK PROTECT引用Tournament和PlayerProfile，(tournament,player)唯一。玩家昵称和用户名仍各自属于原有身份/档案模块，不新建身份体系。

Tournament保存每场独立配置、draft/started状态和创建/更新/启动时间。数据库CHECK约束轮数1～6、正整数点数、非空名称及状态/started_at一致性；参赛关系唯一约束防重复。Uma为JSON十进制字符串数组，API及启动时的模型校验保证四项有限精确数；JSON内容和跨行人数规则由服务校验，不宣称数据库直接约束全部规则。

点数使用PositiveIntegerField（1～2147483647，跨数据库存储边界），Uma输入仅整数/普通十进制字符串（每项最多64字符）；不接受JSON小数，避免解析产生二进制浮点。`rules.canonical_uma`与`derive_oka`可复用，后者用Decimal计算`4*(return-start)/1000`并输出字符串。前端预览使用BigInt整数千分位，最终以后端只读oka为准。不实现实际半庄得分。

每个公开写入口进入transaction.atomic，**第一条数据库语句**执行`UPDATE Tournament SET revision=revision+1 WHERE id=? AND status='draft'`。成功写入先取得共同父行写锁，再读配置和名单；规则PATCH、名单PUT、启动POST均走此入口，不能绕过。PostgreSQL对该UPDATE持有行锁；SQLite在读取前已取得写预留，串行处理写者，不依赖SQLite无效的select_for_update。忙锁返回409 tournament_busy，由用户刷新确认后重试，写请求不自动重放。[Django行锁限制](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update)。

启动重新验证配置和有效人数，锁定账号/昵称来源，bulk_update昵称快照，再写started/started_at，整体提交；任何异常整体回滚含revision。启动后所有外部写入口返回409，昵称显示快照，不随个人资料修改变化。冻结保护是API/服务约束，数据库管理员直接SQL写入不在普通API权限边界内，不宣称不可绕过的数据库历史审计。

全部API使用IsAdminUser、SessionAuthentication、原有CSRF/JSON格式。POST及PATCH支持participant_ids；PATCH可原子修改规则与名单，也保留专门PUT名单接口。选手API增加可选eligible=true筛选有效账号，保持旧响应字段和默认查询行为；前端选择器正确分页和搜索，启动时再次验证有效性。

前端services/tournaments.ts、pages/tournaments.tsx、components/tournament-editor.tsx复用既有API层及shadcn Sheet/Button/Badge，规则/选手分区编辑、摘要、独立启动确认、只读详情；真实接口提供全部业务数据。F0-04阶段仅推导预计桌数、不分配设备；F0-05扩展如下，保留赛事冻结边界。

迁移0001仅新建两张赛事表及约束，无历史迁移改动；在独立QA副本正常migrate。SQLite共享内存及文件事务并发已测试，PostgreSQL实际连接、行锁和并发仍UNVERIFIED。

## F0-02 身份、档案与会话

accounts.User 继承 AbstractUser，AUTH_USER_MODEL=accounts.User，在 accounts/0001_initial 创建。players.PlayerProfile 使用自增 ID、OneToOne(settings.AUTH_USER_MODEL)、nickname(80字符)、created_at、updated_at。身份不混入微信字段；未来外部身份关联应独立设计，本次不实现。

Django auth、sessions 和 AuthenticationMiddleware 管理会话；DRF 采用 SessionAuthentication。注册/登录/退出使用 Django JSON View + csrf_protect，避免匿名 DRF 请求默认不校验 CSRF 的边界。认证 API 成功返回 data，错误返回 error(code/message/fields)；健康接口保留 F0-01 契约。路由错误也转换为 JSON。

Player post_save 创建默认档案（包含 createsuperuser）；注册在 transaction.atomic 内创建 User 与档案并设置独立昵称，失败整体回滚。档案数据库唯一约束防止一人多档案。列表仅 IsAdminUser，GET/PATCH me 只从 request.user 取本人档案，没有按任意用户 ID 修改的接口。

前端 AuthProvider 从 auth/me 恢复身份、通过 Cookie 保持会话；API 服务集中处理 credentials、错误及写前 CSRF 初始化，不自动重试写操作，不持久化密码/Token。Context/Hook 与 Provider 分文件保持热更新边界。登录/注册为公开路由；其余页面需登录；players 还需管理员权限。个人资料位于 /profile。

开发通过同源 Vite /api 代理；本地 CSRF_TRUSTED_ORIGINS 显式为 localhost:5173 和 127.0.0.1:5173。生产采用同源静态站点与 API 反向代理、HTTPS/安全 Cookie，必须显式配置可信来源；不支持通过开放跨域凭据来替代部署配置。

迁移前实查 SQLite 仅有 contenttypes 的两项迁移，未启用旧 auth.User；保存被忽略的备份后正常引入 auth/sessions/accounts/players，无 fake、无旧迁移修改、无数据库重建。开发数据库保留，联调验证账号仅写入独立 .verification 数据库副本。

## F0-03 MahjongMachine 与容量不变量

machines App 分为models（实体/约束）、serializers（输入校验/白名单）、services（事务状态变更）、views/urls（沿用DRF认证权限与JSON规范）。前端services/machines.ts定义契约，pages/machines.tsx负责列表与总览，components/machine-editor.tsx复用现有shadcn Sheet/Card/Badge/Button构建设备表单和退役确认；不新增认证或网络框架。

MahjongMachine.id是自增稳定主键；machine_no是三位数字编号，name(100)、location(200，可空)、description(2000，可空)、status和两个时间戳构成台账。内部capacity_slot仅用于现役容量，不在API中暴露。

| 数据库约束 | 含义 |
| --- | --- |
| capacity_slot唯一，可NULL | 同一现役槽位只能有一台设备，退役设备可有多条NULL |
| 状态/槽位CHECK | 非retired必须拥有1～4非空槽位，retired必须为NULL，无法插入第五个合法现役槽 |
| 条件唯一(machine_no，非retired) | 现役编号唯一，历史编号可复用 |
| 状态/编号/名称CHECK | 状态属于四项枚举，编号三位且只含ASCII数字，名称不能全空白 |

创建时依次尝试四个唯一槽，每次插入独立原子事务；唯一竞争由数据库裁决，不依赖count检查。SQLite忙锁返回可识别的409 machine_busy；不把未知写结果自动重放。编辑/退役在transaction.atomic中进行，PostgreSQL可使用select_for_update；同时使用WHERE status != retired条件更新，避免依赖SQLite无效的行锁来保护终态。退役同时释放槽位并保留原ID、资料。正常API禁止编辑已退役设备或物理DELETE。

状态机：available、maintenance、disabled三者可互相PATCH切换；各非退役状态可经专用POST retire进入retired，retired没有普通出边。machine_no允许现役时规范化编辑，但稳定id不改变。

列表每页20条，默认machine_no/id排序；data包含count/next/previous/results及summary（全库各状态与active计数），统计不受搜索筛选影响。所有端点IsAdminUser，写操作沿用SessionAuthentication CSRF校验。PATCH/POST拒绝id、capacity_slot及其他未知字段。

新增迁移0001建立实体/主要约束；0002补充纯数字CHECK，防止正则末尾换行的数据库边界。两项均正常migrate，未修改F0-01/F0-02迁移。SQLite内存与文件并发已验证；PostgreSQL实连及并发未验证，须在正式环境单独验证。[Django约束参考](https://docs.djangoproject.com/en/5.2/ref/models/constraints/)。

F0-03阶段未建立赛事占用记录；F0-05采用下述MachineAllocation以FK PROTECT引用machineId。capacity_slot仍只表示现役容量，不是占用锁。

## F0-05 轮次、座次与物理资源

实体留在tournaments模块，新增round_services、round_serializers、round_views、table_urls及专门测试；设备共用锁在machines/locking.py。没有新微服务或依赖。

| 实体 | 关系和约束 |
| --- | --- |
| TournamentRound | Tournament FK PROTECT，generated_by User；(tournament,round_number)唯一，编号CHECK 1～6；API仅生成1，服务校验不超过round_count及started |
| RoundTable | TournamentRound FK PROTECT，(round,table_number)唯一，CHECK 1～4 |
| RoundSeat | round、table、TournamentParticipant FK PROTECT；(table,seat_wind)与(round,participant)唯一，wind CHECK四风 |
| MachineAllocation | RoundTable、稳定MahjongMachine FK PROTECT；active machine/table分别条件唯一；active无释放审计、released必须有released_at/released_by；保留编号快照和释放原因 |

RoundSeat.clean与validate_round_structure检查table.round_id=round_id、participant所属赛事一致、每轮全员恰好一次、每桌四风及桌数/连续桌号完整。跨表一致性、精确四人和轮数不超过父赛事由服务保证，不能用普通数据库CHECK表达，不宣称数据库已覆盖；数据库唯一/CHECK兜底其可表达部分。无座次写入API和历史DELETE API。

生成使用Python标准库SystemRandom.shuffle一次，不设置固定生产种子；rng可注入以确定性测试。按冻结名单随机排列，四人一组分别东南西北，原子创建轮/桌/座次及所有占用。available且无active分配的真实设备按machine_no升序选取，不足时整轮拒绝。[Python随机源说明](https://docs.python.org/3.13/library/random.html#random.SystemRandom)。

共同锁顺序：**物理池稳定PK升序 → 赛事行（生成时）→ 子记录写入**。PostgreSQL用有序SELECT FOR UPDATE锁池中已有行；只能分配返回的已锁行，新插入设备在后续请求参与选择。SQLite在任何读取前执行不改值的UPDATE(updated_at=updated_at)，明确获得写预留，再读池；不依赖SQLite无效的行锁。整个池的状态、分配、调整、释放短事务串行协调，适合最多4台现役的当前规模；历史退役行也锁定，规模扩大后另行评估。忙锁返回可识别409，不自动重放。[Django行锁文档](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update)、[条件唯一约束](https://docs.djangoproject.com/en/5.2/ref/models/constraints/#uniqueconstraint)。

machines.services.change_machine首先取同一池锁，再检查active分配；禁止占用设备maintenance/disabled/retired，可改普通资料。生成也先取池锁再检查状态与占用，因此分配与停用/退役竞争只有一种合法提交结果。活动分配唯一约束作为额外数据库兜底，不只依赖count检查或前端。

调整在锁内验证目标存在、available且无占用，原分配写released和审计字段，再创建新active及编号快照；任何失败回滚恢复原占用。同机返回machine_unchanged，不增加历史。释放同样留记录、释放资源，已释放桌不能再调整或重开；释放不写赛事状态、不产生成绩/轮次完结。

新增GET machine-resources返回真实现役状态与active占用、assignable，明确区分available与空闲；这是查询时快照，写入时仍重新检查。全部接口管理员Session/CSRF/字段白名单，旧machines响应字段保持不变。

前端services/rounds.ts、pages/rounds.tsx、components/round-action.tsx复用既有API与shadcn组件。赛事详情提供工作台入口；先刷新真实数据再确认生成/调整/释放；显示四风、设备池、状态和历史，刷新恢复持久化结果。资源不足禁止确认；409保留错误和人工刷新入口，不重试写请求。

第二至第六轮当前明确拒绝，未来仅在上一轮成绩全部确认后使用精确累计积分，每四人一桌、允许重复对手；不能用账号或昵称等替代。F0-06及后续任务另行实现，TBD-001/002保留。

迁移tournaments/0002增四表及约束，保留0001等旧迁移；独立SQLite QA副本正常应用，开发库原样保留。内存和文件SQLite并发分开验证；PostgreSQL实连/并发仍UNVERIFIED，代码中的锁策略不能替代实测。
