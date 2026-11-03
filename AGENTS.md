# Riichi 开发约束

## 项目与职责

Riichi 是前后端分离、模块化单体的 Web 四人立直麻将赛事管理系统。产品范围以 `docs/requirements.md` 为准；Developer 实现 Planner 明确下发的任务，测试和自检不能替代 Planner 的外部验收。

当前任务为 **F0-04 Tournament 赛事领域基础**。仅建设个人赛草稿、独立规则配置、真实选手名单、启动校验及事务冻结；不得实现轮次、分桌、计分、冠军、设备分配或占用调度、取消/删除/完赛、微信或团队赛，不得无关重构账号与选手模块。

F0-01、F0-02、F0-03 已正式验收；当前基线 `baseline/F0-03`，Commit `0d7e96b0b920e490abbf7acd1d4aba38493025f9`，分支 main。不得修改、移动或删除已有基线 Tag。Developer 自检不能替代 Planner 验收。

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

- F0-04 保持当前 `main`，只进行工程实现和验证。**不得自行执行 `git commit`、`git tag`、`git push`。**
- 不修改远程仓库配置，不重写历史，不删除已有文件，不执行破坏性 Git 操作。
- 可以执行 `git status`、`git diff`、`git check-ignore` 等只读检查。
- 本阶段不执行 commit、tag、push，Git 由项目 Owner 手动操作，Planner 负责验收与双基线核验。F0-01、F0-02、F0-03 已建立正式基线，F0-04 尚待验收。详见 `docs/project/baselines.md`。
- 最终报告须列出工程文件、API、界面、启动方法、实际验证、Git 状态、已知问题和自检结论。完成后停止本阶段开发，等待 Planner 验收。

## F0-02 账号安全与迁移

- User 使用 AbstractUser，必须出现在 accounts/0001_initial；PlayerProfile 通过 OneToOne 关联 settings.AUTH_USER_MODEL。注册与档案创建必须原子提交。
- 采用 Django SessionAuthentication；注册、登录、退出为显式 csrf_protect 的 Django JSON View，资料 PATCH 使用 SessionAuthentication 的 CSRF 校验。不得添加 csrf_exempt。
- 前端凭据使用 HttpOnly Session Cookie；每次写请求从 csrf 初始化端点取得当前 Token，仅保留在请求内存，不将认证凭据写入 localStorage，不记录明文密码、Cookie 或 CSRF Token。
- 管理员仅通过 createsuperuser 初始化，无默认管理员密码。权限在服务端检查；注册拒绝敏感字段，普通用户仅改本人昵称。
- 改迁移前先查现有迁移图和数据库，禁止删除数据库、fake 或破坏性重置。兼容异常应停止报告。
- 测试包括事务回滚、唯一约束、权限及真实 enforce_csrf_checks，前端表单/恢复/守卫/角色菜单；联调使用独立测试数据库，不把验证账号作为展示数据。
- 公网上线前另行实现登录限流等加固；F0-02 不实现找回密码、外部认证或微信能力。

## F0-03 设备约束

- MahjongMachine.id 为稳定 machineId，machine_no 为三位数字业务编号；未来赛事以 FK 引用 id，不能按名称或编号关联历史实体。
- available、maintenance、disabled 均占现役容量，最多4台；retired 释放容量但保留原始ID和资料，是普通API不能恢复或编辑的终态。没有物理删除API。
- 数据库使用1～4唯一容量槽与状态/槽位CHECK约束兜底；现役编号使用条件唯一约束。不能仅使用count再insert或仅依赖SQLite不支持的行锁来承诺并发安全。
- 非退役状态可相互调整，退役仅通过专用POST并经前端确认。available仅说明设备状态，不说明赛事空闲或占用。
- 全部设备接口使用现有SessionAuthentication、IsAdminUser与CSRF规则，普通用户/匿名不得读写，内部容量槽不能由请求指定。
- 必须测试数据库约束、并发容量、状态终态、权限、CSRF及原有回归；区分SQLite内存测试、文件测试和未验证的PostgreSQL。
- 所有验证数据和凭据仅放项目内被忽略的独立QA数据库/目录，不把验证设备作为生产演示数据。

## F0-04 赛事约束

- Tournament 独立保存规则；PlayerProfile FK 参赛，(tournament, player) 数据库唯一。昵称在启动事务中保存快照。
- 仅 draft → started；全部外部修改通过 tournaments/services.py，在事务的第一条数据库语句对 draft 父行条件写入，再读取/修改规则、名单或启动。不得绕过此共享写入入口；SQLite 不依赖无效的 select_for_update，忙锁返回409。
- 启动须再次检查配置、4/8/12/16人和有效账号；规则、名单、快照、状态、时间整体提交或回滚。started 无编辑、恢复或删除 API。
- 点数为正整数，Uma 使用整数或十进制字符串输入并保存字符串，Oka 用 Decimal 推导。不得使用浮点计分，不自行要求 Uma 总和或顺序大小，不解决 TBD-001/002。
- 复用管理员 Session/CSRF 与 JSON 错误结构。内部 status、started_at、created_by、revision 和 Oka 只读；选手选择必须查询真实分页API。
- 必测权限/CSRF、配置独立性、四种人数、无效名单、快照、回滚、并发启动及启动/编辑竞态、旧功能回归。独立QA库验证迁移和HTTP；生产 PostgreSQL 未验证不得声称通过。
