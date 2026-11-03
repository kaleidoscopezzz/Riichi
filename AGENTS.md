# Riichi 开发约束

## 项目与职责

Riichi 是前后端分离、模块化单体的 Web 四人立直麻将赛事管理系统。产品范围以 `docs/requirements.md` 为准；Developer 实现 Planner 明确下发的任务，测试和自检不能替代 Planner 的外部验收。

当前任务为 **F0-02 用户账号与选手档案**。仅实现注册、Session 登录退出、个人昵称管理及管理员选手查询。账号身份与选手档案一对一分离，未来赛事通过档案引用；不得实现赛事、设备实体、分桌、计分、微信绑定、团队赛或预先实现 Tournament。

F0-01 正式基线：`baseline/F0-01`，Commit `94a1fec747806682602dd24f7edbbcc4e27d07f0`。不得删除或移动该基线。自检不能替代 Planner 验收。

## 技术与目录边界

- `backend/`：Python 3.13、Django 5.2 LTS、Django REST Framework；开发使用 SQLite，生产预留 PostgreSQL 配置。项目配置、公共服务和未来领域模块保持分离。
- `frontend/`：React、TypeScript、Vite、Tailwind CSS、shadcn/ui、Lucide React。布局、路由页面、通用组件、API 服务和样式分层组织。
- `docs/`：已确认需求、TBD、路线、架构、验证证据和基线制度。新增需求和改变范围须由 Planner 明确确认。
- 不为未来业务建立大量空文件，不引入当前不需要的微服务、Redis、Celery 或基础设施。
- 运行时、虚拟环境、依赖及下载缓存保存在项目目录内。不得擅自安装全局依赖或修改全局环境。

## 实现规则

1. 简体中文为主要界面语言。遵守 Riichi Premium 的深海军蓝、石墨黑、中性色及适度金色/青绿色设计，保持统一组件、间距、字体、边框、圆角和交互反馈。
2. 业务占位须清楚标注尚未实现；不得虚构赛事、选手、成绩或统计数字。请求须有加载、成功、错误和重试反馈。
3. 使用 shadcn/ui 成熟组件作为基础，不另造一套相同用途的组件体系。兼容桌面和手机，关注键盘操作、可访问名称和可读对比度。
4. 密钥、调试开关、允许主机、数据库及跨域来源从环境变量读取；`.env.example` 只包含占位值或安全的本地开发值。
5. 不提交真实密钥、`.env`、虚拟环境、依赖目录、构建产物或本地数据库。不允许全局开放 CORS，也不允许把开发配置作为生产配置。
6. 锁定兼容的稳定依赖并维护可复现记录。依赖升级应说明目的并执行受影响的检查。
7. 先读取相关实现与文档，再做范围内最小修改；保留已有文件和失败证据，不以删除证据掩盖验证问题。

## 验证要求

交付前至少执行并如实记录：

- 后端系统检查、数据库迁移、健康检查自动化测试，以及实际 HTTP 健康响应。
- 前端 TypeScript 检查、生产构建，以及布局和所有基础路由的浏览器检查。
- 前后端健康检查联调，包含正常、加载和失败反馈的检查。
- 敏感信息与 Git 忽略规则检查。

测试须针对真实行为，新增测试与改动风险相称。记录准确命令、执行环境、结果和未验证原因；失败或未执行不得标为通过。PostgreSQL 仅预留配置时，不得声称生产数据库已验证。

## Git 与交付限制

- F0-02 保持当前 `main`，只进行工程实现和验证。**不得自行执行 `git commit`、`git tag`、`git push`。**
- 不修改远程仓库配置，不重写历史，不删除已有文件，不执行破坏性 Git 操作。
- 可以执行 `git status`、`git diff`、`git check-ignore` 等只读检查。
- 本阶段不执行 commit、tag、push，Git 由项目 Owner 手动操作，Planner 负责验收与双基线核验。F0-01 已建立正式基线，F0-02 尚待验收。详见 `docs/project/baselines.md`。
- 最终报告须列出工程文件、API、界面、启动方法、实际验证、Git 状态、已知问题和自检结论。完成后停止本阶段开发，等待 Planner 验收。

## F0-02 账号安全与迁移

- User 使用 AbstractUser，必须出现在 accounts/0001_initial；PlayerProfile 通过 OneToOne 关联 settings.AUTH_USER_MODEL。注册与档案创建必须原子提交。
- 采用 Django SessionAuthentication；注册、登录、退出为显式 csrf_protect 的 Django JSON View，资料 PATCH 使用 SessionAuthentication 的 CSRF 校验。不得添加 csrf_exempt。
- 前端凭据使用 HttpOnly Session Cookie；每次写请求从 csrf 初始化端点取得当前 Token，仅保留在请求内存，不将认证凭据写入 localStorage，不记录明文密码、Cookie 或 CSRF Token。
- 管理员仅通过 createsuperuser 初始化，无默认管理员密码。权限在服务端检查；注册拒绝敏感字段，普通用户仅改本人昵称。
- 改迁移前先查现有迁移图和数据库，禁止删除数据库、fake 或破坏性重置。兼容异常应停止报告。
- 测试包括事务回滚、唯一约束、权限及真实 enforce_csrf_checks，前端表单/恢复/守卫/角色菜单；联调使用独立测试数据库，不把验证账号作为展示数据。
- 公网上线前另行实现登录限流等加固；F0-02 不实现找回密码、外部认证或微信能力。
