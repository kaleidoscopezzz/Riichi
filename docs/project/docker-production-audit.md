# Linux Docker 生产部署：实施前差异审查

审查日期：2026-11-05。基线：`4bc28e5b56b6b82c3ef1ad6b2a54e516eb3bc150`。
已获取 origin/main，指定 infra/docker-production 已存在且与其一致，起点工作区干净。
本任务附件取代 AGENTS.md 中上一轮 Bugfix 的范围、分支及禁止提交限制，其余业务与数据保护继续生效。

| 现状 | 差异与处理 |
| --- | --- |
| Python 声明 3.13.18；Django 5.2.18、DRF 3.18.3、psycopg 3.3.6 全锁定 | 独立生产依赖锁增加 Gunicorn，不改变 Windows 依赖安装流程 |
| base/local/production 分层；base 读本地 .env；生产拒绝 DEBUG、SQLite、空主机及 HTTP CORS | 保留本地设置，生产支持离散 PostgreSQL 参数，明确代理信任边界与安全来源 |
| SessionAuthentication，登录/注册/退出显式 CSRF，前端写前取 token、带 Cookie | Nginx 同源代理，覆盖客户端代理头；登录限流返回统一 JSON 429 |
| production HSTS 一年、includeSubDomains/preload 默认全开 | HSTS 秒数配置、初期 0；子域及 preload 关闭，启用须另经 Owner 批准 |
| 既有 init_admin 委托交互 createsuperuser/changepassword，拒绝提升普通 admin | 直接沿用，入口不创建账号、不迁移、不读旧 QA 凭据 |
| 健康 API 是无数据库 liveness | 容器探针增加数据库连接及待迁移检查，避免把 liveness 当 readiness |
| staticfiles 已配置；无 Django admin 页面/模板 | API 不需要静态资源；React dist 由 Nginx 提供；保留原静态配置，不在只读运行容器写静态文件 |
| Vite 8.3.5；Node >=22.12、npm >=10；锁文件；BrowserRouter | 多阶段 npm ci/build，同源空 VITE_API_BASE_URL，SPA 回退仅用于前端 |
| 无部署文件或数据生命周期脚本 | 新增三服务 Compose、TLS、独立迁移/备份/恢复脚本及运行手册 |

数据库审查覆盖 accounts/players/machines/tournaments 模型、迁移、服务锁和计分。
未发现业务迁移使用 RunSQL、PRAGMA、SQLite 原生 SQL；条件唯一约束、正则 CHECK、事务均由 ORM 表达。
SQLite 的资源池空写仅在 `connection.vendor == 'sqlite'` 执行，PostgreSQL 使用稳定主键顺序的 SELECT FOR UPDATE。
赛事配置写使用条件 UPDATE 锁父行；选手身份锁顺序为 User → Profile。未见锁 nullable 外连接的问题。
精确计分使用 JSON 中的有理数字符串/分子分母，不转 float；JSONB 转换后的对象键顺序不能作为业务排序依据。
跨表座次完整性依靠服务验证，不宣称由 CHECK 全部保证。

`verification/migration_check.py` 的 PRAGMA 是独立 SQLite 验证工具，不能直接在 PostgreSQL 执行。
实施阶段须在隔离 PostgreSQL 跑全量测试、正常迁移、HTTP 赛事和备份恢复，并保留实际失败；若出现兼容缺陷，只修当前服务/验证，不改历史迁移。
Owner 数据库、旧 QA 凭据、历史报告、Windows 入口均不作为本次验证输入。

实施依据：[Django 5.2 设置](https://docs.djangoproject.com/en/5.2/ref/settings/)、[Compose 健康依赖](https://docs.docker.com/compose/how-tos/startup-order/)、[Nginx 限流](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html)、[PostgreSQL 恢复](https://www.postgresql.org/docs/17/app-pgrestore.html)。
