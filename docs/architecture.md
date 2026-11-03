# 工程架构

## 技术与边界

Riichi 使用前后端分离、模块化单体。浏览器运行 React 应用，通过版本化 HTTP JSON API 访问 Django/DRF；开发环境数据库为 SQLite，正式环境预留 PostgreSQL。

| 层 | 技术 | 职责 |
| --- | --- | --- |
| Web | React、TypeScript、Vite | 路由、布局、页面状态和 API 交互 |
| UI | Tailwind CSS、shadcn/ui、Lucide React | Riichi Premium 设计变量、基础组件与图标 |
| API | Python 3.13、Django 5.2 LTS、DRF | 版本化接口、配置及公共服务 |
| 存储 | SQLite / PostgreSQL | 本地开发 / 正式环境预留 |

当前只实现健康检查公共能力，不创建赛事业务数据库模型、注册认证端点、Tournament 类或计分算法。后续领域模块在任务明确后按责任加入，不提前堆积空目录。

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
| `/players` | 选手管理占位 |
| `/machines` | 麻将机管理占位 |
| `/settings` | 系统设置与基础信息 |
| 其他路径 | 未找到页面 |

开发时，浏览器访问本地 Vite，`/api` 由 Vite 代理到 `http://127.0.0.1:8000`。Django 的直接跨域访问仅允许明确配置的本地 React 来源，禁止通配放行。生产需由部署环境提供前端静态资源与 API 转发/来源配置，Vite 开发服务器不作为生产服务。

健康请求显示加载、成功或失败状态，并支持重试。仪表盘不以虚构数据填充统计卡片。业务占位说明功能边界，不能呈现已创建赛事或已注册选手的假象。

## Riichi Premium

基础为深海军蓝、石墨黑和中性色，使用适度金色或青绿色强调。统一 Typography、Spacing、Radius、Border、Shadow 与 Hover，通过主题变量管理。默认暗色并预留亮色切换；桌面采用侧栏布局，窄屏保证导航和主内容可访问。避免无意义渐变、过量动画和装饰性统计图。

## 后续扩展原则

账号、选手、设备、赛事、分桌和成绩能力按后续任务逐步落地；业务规则不进入页面组件或公共 health 服务。Tournament 未来作为独立赛事实例的领域对象设计，数据库持久化与 API 应遵从领域边界。微信能力留在未来版本规划，不在当前引入依赖或空模块。
