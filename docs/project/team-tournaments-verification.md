# 团队赛实现与验证

日期：2026-11-10。基线main `8f94f2e`，工作分支`codex/team-tournaments`。Owner已明确授权“实现功能并测试通过”，并确认TEAM-01～13，规则见[团队赛文档](../team-tournament-plan.md)。实现、本地验证与独立复核已完成；本报告不改判历史验收，候选未正式验收/未上线，Git提交、Push/PR和CI尚未执行。

## 实现范围

- 可变队伍及不等人数阵容；既有PlayerProfile/内部User身份不变，同一赛事成员只能属一队。启动冻结队伍、成员和昵称，进行中只修改未来未开场名单。
- 自由总桌场次和固定位置循环。默认先锋→次峰→中间→副将→大将，每位置每队2场，可配置场数/循环和位置列表；每桌四支不同队伍各一人，各队等场。5/7队K=2明确拒绝并提示K=4，不自动改配置。
- 均衡随机或手动四队分组；队长线下指定、管理员录入。计划草稿/确认/撤回/开场和位置代表均有版本及审计；同队不同人可并发，同一人不能同时两桌，同周期同位置首次开场锁定代表。
- 1～4张真实物理桌，跨赛事共享、单赛事不重复、维护/停用不可选、故障换桌及完赛释放本赛关联。实际时段只使用连续可开场计划，不跳场、不越过未完成位置。
- Fraction团队积分求和、成员贡献、真实个人辅助统计、每队位置进度；实时显示个人积分及团队当前/变化/试算后积分。后续时段已开始仍可更正早场数字，既有人员/座次保留，完整更正历史留档。
- 团队总分→第一合计→第二合计→公开团队抽签；团队实体冠军及冻结最终结果。个人辅助榜可并列、未出场不排名，不要求额外个人抽签。团队淘汰、桌附加分、个人奖和微信未加入首版。

## 环境与隔离

Windows、PowerShell；Python 3.13.15 / Django 5.2.18，既有验证虚拟环境；Node 22.23.4 / npm 10.9.9及仓库锁定依赖。未新增依赖、未全局安装。数据库、证书、日志、临时文件和缓存在忽略的任务QA目录中。

后端环境为`RIICHI_LOAD_DOTENV=0`、每个任务随机生成SECRET_KEY，`DATABASE_URL=sqlite:///<workspace>/backend/.verification/team-tournaments/<qa-name>.sqlite3`；TEMP/TMP及npm缓存位于项目`.cache/team-tournaments`。不加载Owner的.env、不定位或写入Owner数据库，不使用历史管理员凭据。

浏览器QA由专用脚本生成80名QA选手、4张设备、既存瑞士历史夹具及随机管理员密码。HTTPS只绑定localhost/127.0.0.1/::1:18455，后端仅127.0.0.1:18095；私有临时证书只用于该loopback QA。测试凭据、数据库、证书私钥及Playwright trace均保持忽略，不进入公开证据。

## 已执行的最终检查

| 检查 | 实际命令 | 结果 |
| --- | --- | --- |
| Django系统检查 | `python manage.py check` | PASS，无问题 |
| 正常空库迁移 | `python manage.py showmigrations --plan`，`python manage.py migrate --noinput` | PASS，独立validation-final.sqlite3正常迁移至0014；未fake/清库 |
| 模型与迁移一致 | `python manage.py makemigrations --check --dry-run` | PASS，No changes detected |
| SQLite后端全量 | `python manage.py test --verbosity 1` | PASS，256项，86.718s；包含最终历史阶段写保护及位置手动分组回归 |
| 前端全量 | `npm test` | PASS，21文件260项 |
| TypeScript与构建 | `npm run build` | PASS，包含两个tsconfig类型检查；保留584.44kB JS包超过500kB的构建提示 |
| 依赖安全审计 | `npm audit --registry=https://registry.npmjs.org --json` | PASS，0漏洞；未执行自动升级 |
| 团队浏览器复测 | `npm run test:e2e -- --config ../.verification/team-tournaments/playwright.second.config.ts e2e/team-tournaments.spec.ts` | PASS，4项，3.1m；含6队24人自由赛、20场两循环、奇数队校验和手机深浅主题Select |
| 全套浏览器与失败保留 | `npm run test:e2e -- --config ../.verification/team-tournaments/playwright.final.config.ts` | 12 PASS / 1 FAIL，10.4m；个人9项通过，团队新增积分截图断言发生title子串定位错误，原日志/截图保留 |
| 最新团队浏览器 | `npm run test:e2e -- --config ../.verification/team-tournaments/playwright.candidate.config.ts e2e/team-tournaments.spec.ts` | PASS，5项，3.4m；修正精确定位并增加固定位置手动分组，使用新QA库及新输出目录 |
| 应用HTTP/Session/CSRF | 专用loopback HTTP脚本 | PASS，15项；Session Secure/HttpOnly、CSRF Secure，匿名/缺CSRF/外部Origin/非法Host/越权及严格字段检查 |
| 忽略、diff与证据敏感检查 | `git diff --check`、`git check-ignore`、源码敏感模式扫描及证据白名单/凭据值扫描 | PASS；119份证据及64项源码/依赖锁清单，无凭据/私钥/数据库/trace入库 |
| CI helper语法 | Python AST解析browser_seed、嵌入fixture及postgres_migration_check | PASS，语法及调用边界核验；Docker/PostgreSQL实际运行仍UNVERIFIED |

命令通过既有项目工具运行；前端test:e2e先执行`tsc --noEmit -p tsconfig.e2e.json`。详细日志已登记于[证据目录](evidence/team-tournaments/)，原始未删改日志仍在忽略的QA目录。

浏览器共14个独立场景在本轮分次完成：个人9项由全套运行通过，团队5项由最终候选复测通过。全套命令原先12 PASS/1 FAIL的记录保持原样。之后仅修改团队手动入口及其测试/历史阶段保护，个人实现未改，不重跑已通过的个人场景。

已归档[最终后端全量](evidence/team-tournaments/logs/backend-full-release-candidate.log)、[前端全量](evidence/team-tournaments/logs/frontend-full-candidate.log)、[团队浏览器复测](evidence/team-tournaments/logs/browser-candidate.log)、[全套原始失败记录](evidence/team-tournaments/logs/browser-final.log)、[HTTP结果](evidence/team-tournaments/summaries/http-security-final.json)、[迁移结果](evidence/team-tournaments/summaries/migration-summary.json)及截图。候选身份见[源码清单](evidence/team-tournaments/source-manifest.json)，证据SHA-256见[证据清单](evidence/team-tournaments/evidence-manifest.json)。

## 兼容迁移与主要回归

只新增tournaments/0011～0014，0001～0010及其他历史迁移未编辑。团队冠军、抽签作用域、阵容/计划来源及每队代表来源为新增字段/实体。原round_count非空、PositiveSmallInteger及轮号列类型在最终迁移状态保留；团队API使用null表示不套个人轮数，实际计划/时段使用团队配置，个人1～6轮限制仍有效。

独立带数据QA在0010处建立原列/类型/行/外键投影，备份后正常升级至当前迁移，再从备份独立恢复、核对原投影并升级恢复库。实际结果：原列类型/行/FK及历史默认PASS，旧个人赛/抽签类型正确，无虚构团队数据，重跑幂等，备份integrity_check=ok，独立恢复及恢复库升级PASS。备份SHA-256：`6acea5d9b51b065f34dbb205d61ae47b8f7d3d80e5326a62620a8c66fefc81a0`。备份本体不提交。

原迁移演练helper原先以当前leaf作为历史阶段目标，会在新增团队表后混用当前模型与旧图；本轮将review/Oka/pairing/event-flow各helper限定在自己的0006/0007/0009/0010，并使用历史app模型。PostgreSQL CLI在历史review演练后显式正常升级至leaf，再查询当前模型；不改历史迁移、隔离库限制或历史证据。最终256项包含这些迁移回归、原个人全流程与团队32项排程/API/真实并发检查。

CI的专用browser_seed增加到80名隔离QA选手，满足团队24人场景；个人场景仍使用自己的原名单切片，未改业务选手上限。该脚本语法及隔离保护已核对，Linux/Docker运行留待真实CI。

团队回归覆盖可变名单超过16人、5队完整等场完赛、4队五位置两循环20批、5/7队K=2拒绝/K=4合法、兼任/下循环换人/位置锁定、同队不同人并发及同人冲突、自由及位置手动分组/配额、清空代表/确认撤回/原来源、撤回阶段禁止再写及事务回滚、新阶段仍可编辑、51场分页、严格字段、团队/个人操作隔离、Session/CSRF、成绩草稿不计分、三份50/3精确合计50、团队实时累计280/3、旧成绩更正、团队抽签待确认/作废/来源过期、完赛只读和共享设备的单赛释放。

## 失败记录与独立审查

本轮保留所有原始失败记录，后续通过不能删除或改写早期失败：

1. 早期后端全量发现历史helper目标与团队图不兼容，并发现个人写入口新增只读派发破坏原SQLite首写锁顺序；已限定历史目标，并将类型派发放在View，恢复原个人服务入口。后续全量255项包含原并发/迁移回归。
2. 最初备份integrity_check的raw SQLite连接缺少REGEXP注册；随后使用Django SQLite注册函数在独立连接核验，原备份保留。
3. 首次团队浏览器运行失败：第8场后位置刷新尚未完成，打开了旧副将面板；无合法赛程的草稿工作台又因ValidationError返回400。已在刷新时禁用位置操作、让未生成草稿正常读取；第二次完整4项均通过。首轮失败截图及私有trace保留，未复用或覆盖输出目录。
4. 独立Reviewer初审发现P1完赛DTO缺mapping致页面崩溃、P2清空位置代表未提交、P2过期确认面板继续旧来源。已补完赛读取字段且保留冻结成绩、支持null清空及审计、409禁用旧确认并显式回读原场次/位置；补API、前端和完赛后页面重载回归。审查修复后后端18项及前端13项通过，最终全量包含这些用例。
5. 新增测试的两次失败属于用例调用错误：完赛heading层级/刷新后的LastCall断言，以及个人generate的关键字参数/作废接口不接受confirmed。按真实契约修正，未改变业务接口以迁就断言。最后全量均通过。
6. 全套浏览器13项第一次12通过/1失败；新增`getByTitle('0/1')`默认子串匹配把`40/1`也选中，真实显示0.00/40.00/40.00正确。两个定位器改为exact，未改积分算法；原失败日志、截图及私有trace保留，最新团队复测另存目录。
7. 独立复核追加两项P2：reset后的旧阶段代表仍可用旧ID写入，固定位置的手动策略缺分组UI入口。已用有效计划引用限制阶段写入，single/bulk拒绝后代表/来源/计划/revision/审计全部不变；新赛程新阶段仍可编辑。位置手动UI现在仅提交四队，人员由本位置代表映射，阶段各队K场校验保留，补组件/页面/API及浏览器场景。

独立Reviewer `/root/team_reviewer` 已给出最终结论：**本轮Windows／SQLite／Edge／loopback QA范围复核通过，未发现未修复的源码阻断项**。五项问题均有实际回归，64项源码及119份证据SHA-256全部一致，后端256项、前端260项、HTTP15项及个人9／团队5项浏览器分次结果与报告一致，未发现凭据、私钥、数据库或trace混入。Reviewer未编辑文件、执行数据库写入或访问服务器；PostgreSQL、Linux/Docker、CI、Owner库及生产仍保持UNVERIFIED。

交付前再次核对源码与证据全部SHA-256无变化，`git diff --check`通过，既往迁移与依赖锁无diff。所有自建QA后端/HTTPS助手经任务目录stop文件正常结束，进程返回0；loopback 18095/18455监听均已关闭。QA原库、备份和失败证据保留，不影响其他进程或Owner环境。

## UNVERIFIED与停止边界

本机未找到可用PostgreSQL、Docker/Podman；WSL未提供可用发行版。本轮PostgreSQL双库、Linux容器和GitHub CI未实际运行，保持UNVERIFIED，历史报告不能替代本轮验证。256队/4096成员/10000场为防滥用技术配额，未宣称规模上限压测通过。

Owner库、真实服务器、Caddy公网证书/续期及生产迁移/部署未验证。本轮仅代码、文档及隔离QA；未连接正式服务器、未初始化或修改实际管理员、未提交/Push/创建PR或合并。正式验收与发布另按Owner授权推进。
