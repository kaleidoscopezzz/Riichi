# 进行中跨轮成绩更正与实时积分验证

Owner于2026-11-07要求：赛事进行中，第二轮开始后仍可修改第一轮成绩，并在修改数字时实时展示成绩和积分。本次执行日期2026-11-09；起点main `06feff51bdda8decbec531ef7d4397a0279f1eff`，工作区干净，Oka扩展已包含在基线。本次分支`codex/score-corrections`。

## 行为与边界

- 任意已存在轮次的未确认成绩可继续录入；已确认成绩使用“更正成绩”入口，一次保存更新正式积分，说明可选。四人严格整数、固定总点数、当前版本和管理员Session/CSRF校验保持。
- 更正保持confirmed状态，原子更新该桌分数/版本/编辑确认信息，TableResultCorrection保留前后完整原点数、精确积分及规则/编辑确认快照，并记录操作者和时间。相同数值不增加成绩版本或更正记录。
- 已生成轮次的ID、参赛者、四风、分桌依据和物理桌快照保留；新累计分及第一/第二次数用于后续尚未生成轮次。旧抽签保留原文，来源版本过期后不参与当前排名；完赛仅引用实际采用的抽签记录。
- 数字编辑使用同一整数解析器和只读服务端Fraction试算。部分输入可看基础分，异常合计可看完整试算，但不得确认/保存更正；试算不写成绩、版本、审计或排行榜。150ms请求、Abort及输入标识防止旧响应显示在新输入下，CSRF获取步骤同样可取消。
- 完赛后禁止更正，历史可查询。过期版本拒绝，不自动回放写操作，提供载入最新成绩入口；保存后保持当前查看轮次。

新增迁移`0008_result_corrections`只创建审计表，含FK PROTECT、同结果前后版本唯一及连续版本CHECK；没有回填或改动0001～0007。本轮仅写忽略目录中的独立QA及备份/恢复副本；未迁移业务库、读取旧QA密码或连接正式服务器。

## 实际环境与命令

Windows / PowerShell 7.6.9；Python 3.13.15 / Django 5.2.18 / DRF 3.18.3 / SQLite 3.53.1；项目内Node 22.23.4 / npm 11.19.1 / Playwright 1.65.0；本机Edge（Chromium）157.0.4341.42。依赖和锁未变更。

后端在backend执行，解释器为既有`D:\Riichi\_tools\cov-venv\Scripts\python.exe`；显式设置`DJANGO_SETTINGS_MODULE=config.settings.local`、`RIICHI_LOAD_DOTENV=False`、随机QA SECRET_KEY、`DATABASE_URL=sqlite:///.../backend/.verification/score-corrections/...sqlite3`与本机允许主机。前端临时文件和npm缓存保留在项目忽略目录，构建明确采用相对API地址。

| 验证 | 实际命令/范围 | 结果 |
| --- | --- | --- |
| 系统/迁移 | `manage.py check`、`makemigrations --check --dry-run`、`migrate --noinput` | PASS；正常应用0008，无遗漏迁移 |
| 后端全量初轮 | `manage.py test --noinput` | PASS，176项；随后审查增加读取竞态修复/回归 |
| 最终后端全量 | `manage.py test --noinput` | PASS，179项，44.610秒 |
| 更正及原竞赛专项 | `manage.py test tournaments.tests_result_corrections tournaments.tests_competition --noinput` | 修复同源读取后54项PASS |
| 最终更正专项 | `manage.py test tournaments.tests_result_corrections --noinput` | PASS，20项，含3项可控读取竞态回归 |
| TypeScript/Vitest | `npm run typecheck`、`npm test`、`tsc --noEmit -p tsconfig.e2e.json` | PASS；15文件、213项Vitest |
| 构建/审计 | `npm run build`、`npm audit --audit-level=high --registry=https://registry.npmjs.org --cache .cache/npm` | PASS；0漏洞；保留单JS块超过500kB的构建提示 |
| 备份/独立恢复 | `.verification/score-corrections/check_migration.py`调用[迁移演练](../../backend/verification/result_correction_migration_check.py) | PASS；旧结果/抽签/分桌/分配/预留原列及关系不变，审计初始空表，恢复后正常升级、幂等重跑通过 |
| 实际HTTP/UI专项 | `score-corrections.spec.ts`，8人3轮、R2一桌已有确认成绩后更正R1 | PASS，首次31.8秒；预览期间原成绩不写入、合计错误禁保存、更正排名、R2完整数据不变、后续分桌/审计/完赛/完成后409、320/390/1440深浅主题 |
| 真实浏览器全量初轮 | `npm run test:e2e -- --config=../.verification/score-corrections/playwright.local.config.ts --output=../.verification/score-corrections/browser-full` | 3用例PASS，3.5分钟，覆盖Oka、4/8/12/16人及16人6轮；运行实例为审查读取修复前代码 |
| 最新代码浏览器首次复验 | 同上，输出改为`browser-final`，新建隔离QA实例以加载最新后端 | 1通过、2失败；记录见下，未将整轮标PASS |
| 最终浏览器复验 | 同上，输出改为`browser-rerun`，再次使用全新隔离QA | 3用例PASS，3.5分钟；Oka34.9秒、原完整赛事2.4分钟、更正27.1秒 |
| 独立审查 | `/root/score_corrections_reviewer` | 最终源码及证据复核PASS，无待修复项；原P1已解决，失败/原图保留 |
| 范围/秘密/忽略 | `git diff --check`、锁/历史迁移范围、`git check-ignore --no-index`、生成QA秘密扫描 | PASS；包括最终报告、日志及截图范围 |

原始日志在`backend/.verification/score-corrections/`，可分享证据汇总至[evidence/score-corrections](evidence/score-corrections)。QA账号/密钥/数据库/备份、浏览器Cookie及trace保持忽略。更正试算、历史和完赛截图只展示本轮隔离QA的真实API数据。

主要记录：[最终后端179项](evidence/score-corrections/backend-full-final.log)、[前端213项](evidence/score-corrections/frontend-full-first.log)、[最新代码浏览器最终3项](evidence/score-corrections/browser-rerun.log)、[备份恢复摘要](evidence/score-corrections/migration-summary.json)、[独立审查读取竞态回归](evidence/score-corrections/backend-read-race.log)。早期成功与失败日志同时保留，未用历史PASS替代本轮执行。

最终界面：[桌面浅色实时试算](evidence/score-corrections/correction-preview-1440-light.png)、[320深色](evidence/score-corrections/correction-preview-320-dark.png)、[更正记录](evidence/score-corrections/correction-history.png)、[完赛结果](evidence/score-corrections/correction-completed.png)。三种尺寸与深浅主题均有截图及横向溢出断言；更正记录图等待弹层几何稳定后再拍摄。

浏览器配置复用仓库localhost HTTPS与QA凭据限制，仅选择已安装Edge和独立输出目录；使用新生成的本机证书及临时TLS静态/API代理访问隔离Django/SQLite。该结果不等同于Caddy/Nginx/PostgreSQL生产链路验证。所有实例仅管理本任务创建的服务，完成后按本实例停止标记正常退出，不按程序名终止进程。

## 独立审查发现及修复

**P1：榜单与完赛令牌必须来自同一批成绩。** 初版工作台先计算排行榜，随后另查source_versions；若另一管理员在二者之间更正，可能显示旧榜单却携带新版本，使后续完赛接受与管理员看到的内容不同的结果。独立Reviewer要求修改，开发者未以当时全量通过代替审查。

修复将已确认结果一次加载为同一批对象，排行榜、抽签适用性、完成标志和source_versions均从该批派生，不取得写锁、不额外写库。三个patch控制竞态用例分别验证：排名读取后更正仍返回旧榜单/旧令牌且完赛409；读完空批次后有人首次确认不能把旧预览标为完整；HTTP工作台与后续完赛同样拒绝过期令牌并保持started/无最终快照。修复复核PASS，最后候选另跑全量验证。

旧UI“再次确认并锁定成绩”按新需求改为“再次确认成绩”；原有重复确认拒绝、整数/总和/权限/CSRF、草稿、分桌、抽签与完赛有效断言保留。移除仅允许最后轮次录入的限制，增加进行中更正及历史未确认轮次回归；原历史报告和证据未改写。

## 保留的失败及未验证项

- 首轮后端专项51项中1项失败：测试DELETE历史接口漏发CSRF，得到403；补正确CSRF后验证只读接口的405。原`backend-targeted-first.log`保留，不将整轮标PASS。
- 最新代码浏览器首次复验在16人6轮中遇到生成请求跨过默认5秒UI断言窗口，原记录显示请求尚未完成，事务随后201成功且页面进入第4轮；该场尚未完赛，4张桌仍占用，造成后续专项等待选桌而超时。未清理或篡改该QA库；保留`browser-final.log`、失败截图及私有trace，改为等待实际HTTP响应/检查成功状态后保留原UI断言，并在新QA库重跑。选项增加可见断言，避免缺少资源时等待整个10分钟用例。
- 首次更正历史截图采到了Sheet展开动画途中，图中弹层尚未完全进入视口；增加等待几何稳定/视口边界检查后再截图，原图保留。该修正不变更产品交互或安全检查。
- 上一Reviewer因服务繁忙失败，未产出审查通过结论；重新安排独立Reviewer完成源码审查，保留P1发现和修复过程。
- 本轮PostgreSQL、Linux Docker/Caddy/Nginx集成、GitHub CI与正式业务库/服务器均为 **UNVERIFIED**。未把Oka或生产上线历史验证计作本轮PASS。
- 工作分支本地修改；本轮未提交/推送/创建PR/合并/部署或创建验收Tag。业务库应用0008仍需按现有备份、独立恢复核对和迁移计划流程操作。
