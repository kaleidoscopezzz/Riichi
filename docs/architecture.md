# 工程架构

## 技术与边界

Riichi 使用前后端分离、模块化单体。浏览器运行 React 应用，通过版本化 HTTP JSON API 访问 Django/DRF；开发环境数据库为 SQLite，正式环境预留 PostgreSQL。

| 层 | 技术 | 职责 |
| --- | --- | --- |
| Web | React、TypeScript、Vite | 路由、布局、页面状态和 API 交互 |
| UI | Tailwind CSS、shadcn/ui、Lucide React | Riichi Premium 设计变量、基础组件与图标 |
| API | Python 3.13、Django 5.2 LTS、DRF | 版本化接口、配置及公共服务 |
| 存储 | SQLite / PostgreSQL | 本地开发 / 正式环境预留 |

当前提供健康检查、F0-02 账号/选手档案及 F0-03 设备资源台账能力，不创建赛事模型、Tournament 类或计分算法。后续领域模块在任务明确后按责任加入，不提前堆积空目录。

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
| `/tournaments` | 赛事管理占位 |
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

账号、选手、设备、赛事、分桌和成绩能力按后续任务逐步落地；业务规则不进入页面组件或公共 health 服务。Tournament 未来作为独立赛事实例的领域对象设计，数据库持久化与 API 应遵从领域边界。微信能力留在未来版本规划，不在当前引入依赖或空模块。

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

未来Tournament每轮逻辑桌次应以ForeignKey引用machineId，并为历史追溯选择保护策略（例如PROTECT）；界面显示编号，可按编号顺序选择available设备。防止时间冲突、跨赛事占用、MachineAllocation、RoundTable等均留给后续任务，本次没有建立这些表或锁。capacity_slot不是赛事占用锁。
