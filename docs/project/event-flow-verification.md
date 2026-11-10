# 赛事展示、共享桌与逐轮淘汰验证

Owner于2026-11-10确认：成绩展示更清楚；月赛、日赛可同时关联同一可用麻将机；每轮结束管理员可预览确认淘汰累计排名末四人，每轮最多一桌，至少保留四人打完所有剩余配置轮次。固定“第三轮后自动淘汰”不是本轮规则。新建赛事简化为手动、完全随机、高高碰，既有瑞士赛事保留冻结策略。

工作分支`codex/event-flow`，起点main `469f38f`。前轮已独立审查的麻将机自动编号改动保留在工作区，未覆盖选手页面、Owner资料或历史迁移。本轮未执行提交、推送、PR、合并或部署；GitHub CI和正式业务库/服务器单列UNVERIFIED。

## 实现与规则

- 累计榜与逐轮明细展示两位小数，基础积分、Uma/Oka顺位奖励和本轮积分分列，精确分数可展开。手机使用纵向卡片。后端排名和累计始终使用Fraction，前端BigInt只格式化展示。
- 三项真实统计：四位回避率最高、单个半庄最高终局点数、当桌第一次数最多（吃1）。仅用已确认成绩，包含已淘汰选手的已打半庄，所有并列领先者均展示。共享名次第4才计四位；并列第三不计第四、并列第一均计吃1。没有和牌累计打点数据，页面明确展示终局点数。旧最简快照缺少逐轮数据时统计为空，不补造次数或重算完赛积分。
- 新Reservation作为赛事关联，跨赛事可共享；同赛事不重复选机、维护/停用/退役设备不可选。资源API返回全部关联，结束一场仅结束该场关联。旧MachineAllocation身份、约束、分配与释放历史保留。
- 当前及此前已生成轮次均全确认、尚有下一轮、仍在赛人数大于4时可选择淘汰；直接生成下一轮表示本轮不淘汰。淘汰边界完全并列要求公开抽签、二次确认，再另行确认四人名单。记录完整服务端成绩/资格来源、排名、抽签、确认人和时间。
- 淘汰保留原参赛关系、昵称和成绩，新轮只安排active子集，初始完整随机序列不改。多余逻辑桌保留，关联留痕结束，其设备可用于剩余桌故障替换。更正不自动复活、不覆盖已有座次；冠军来自完成剩余赛程者。淘汰阶段较晚者排在较早者之前，同阶段继续用原performance指标。
- 抽签按purpose及轮次区分，来源必须匹配，保留原作废/确认审计。榜单、统计、淘汰预览、成绩版本和资格版本由同批对象派生；事务内拒绝过期来源和名单。

## 迁移与数据保护

新增`0010_event_flow`：EliminationRecord、参赛者淘汰轮次、抽签用途/轮次/资格来源及同表约束；仅移除新Reservation的全局机器唯一索引，逻辑桌唯一及释放审计保留。0001～0009原迁移不变；0009历史演练固定在0009目标。

先创建并备份独立0009基线，后正常migrate到0010。带数据演练包含进行中瑞士赛事、已完赛赛事、长精确小数、确认成绩、更正、抽签、原座次、旧分配及关联，比较所有原字段/时间戳/主键/FK/快照。SQLite backup、完整性检查、独立恢复、恢复库升级、再次迁移均PASS；没有虚构淘汰，旧资格NULL、旧抽签用途final。摘要见[迁移证据](evidence/event-flow/migration-summary.json)。

只读盘点未找到默认`backend/db.sqlite3`，未定位实际Owner库；实际Owner库/生产库状态为UNVERIFIED。本轮只写忽略目录中的新QA库及副本。

## 实际执行

Windows PowerShell；Python3.13.15/Django5.2.18，项目内Node22.23.4/npm11.19.1、Playwright1.65.0和已安装Edge。QA关闭dotenv，独立随机SECRET_KEY/账号、新SQLite、私有localhost证书、凭据、缓存和trace均在忽略目录；未连接正式服务器。

后端环境：`RIICHI_LOAD_DOTENV=0`、每进程新随机64字符测试密钥、`DATABASE_URL=sqlite:///.verification/event-flow/baseline.sqlite3`。实际使用已有隔离Python，非全局安装；Node/npm使用`.tools/node-v22.23.4-win-x64`，TEMP/TMP指向`.cache/event-flow/tmp`。

| 检查 | 本轮结果 |
| --- | --- |
| Django check / makemigrations --check --dry-run / 正常migrate | 修正候选已执行，0问题、无迁移漂移、QA已到0010 |
| Django全量 | PASS，最终候选223项，退出0 |
| TypeScript / Vitest / build | PASS，两个TypeScript项目、e2e类型检查、17文件235项及生产build均退出0；Vite单包超过500KiB提示记录保留 |
| npm audit --audit-level=high --registry=https://registry.npmjs.org | PASS，0漏洞；未改全局注册源或依赖锁 |
| 带数据迁移、备份及独立恢复 | PASS |
| HTTP Session / CSRF / TLS / 私有缓存 / 白名单 | PASS，最终新QA环境已复核 |
| 真实Edge浏览器 | PASS，最终9项、7.7分钟，320/390px明细卡片视口边界和table语义、深浅主题、淘汰后空桌故障复用均通过 |
| git diff --check / 历史迁移 / 密钥与忽略检查 | PASS，旧迁移/依赖锁未改；QA库、凭据、证书私钥、构建、缓存和trace均被忽略，公开证据无QA密码或私钥 |
| 独立审查 | 终结PASS，无待修复项；4项P2已闭合，24关键源码/43全部源码指纹均匹配 |

最终命令分别为`python manage.py check`、`makemigrations --check --dry-run`、`migrate --noinput`、`test --noinput`，以及`npm run build`（含两个TypeScript项目）、e2e TypeScript检查、`npm test`、官方源audit、受localhost隔离配置保护的Playwright全套。实际stdout和退出结果存入[evidence](evidence/event-flow/)。

最终浏览器同时回归Oka零/精确小数、8人月赛/4人日赛共享、16人6轮可跳过淘汰、边界公开抽签、第二轮开始后更正第一轮且不复活、手动鼠标/键盘/触屏分桌、既有瑞士策略、4/8/12/16人完赛及登录/退出。16人逐轮人数为16/16/12/12/8/4，第2/4/5轮确认淘汰，原随机序列及历史座次保留；第5轮后复用已空出的D桌设备供A桌故障替换，旧轮机器快照仍为原值。

最终独立QA后台及HTTPS辅助服务已通过各自任务目录的stop标记正常退出，两个进程均退出0；没有按进程名/PID终止其他进程。QA数据与原失败trace保留在忽略目录。

代表截图：[桌面统计与明细](evidence/event-flow/statistics-rounds-1440-light.png)、[390px深色卡片](evidence/event-flow/statistics-rounds-390-dark.png)、[320px浅色卡片](evidence/event-flow/statistics-rounds-320-light.png)、[新赛事策略展开](evidence/event-flow/strategy-select-390-dark.png)、[淘汰确认预览](evidence/event-flow/elimination-preview-desktop-light.png)。当前源码指纹见[source-sha256](evidence/event-flow/source-sha256.json)，私有DB/credentials/trace没有复制到该目录。

## 独立审查及失败记录

保留所有历史报告、原有效测试和本轮失败证据，没有删失败用例。本次覆盖冲突旧断言：跨赛事占桌互斥改为共享，同赛事不重复仍验证；新建瑞士改为既有瑞士兼容，原算法/权限/已启动冻结验证保留；参与者白名单增加淘汰轮次，内部用户名仍禁止；积分显示增加单位，负零/负分母/非法分母保护仍验证。

独立Reviewer初审无P1，发现4项P2并修正：

1. 同成员跨轮时旧淘汰抽签面板继续录入：现在同时匹配轮次，回读后仅展示旧轮历史；补跨轮回读回归。
2. 瑞士草稿被改成高高碰后回读仍有旧瑞士选项：现在按最新base构造选项；补并发回读回归。
3. 首次淘汰接受空资格来源并存入审计：新淘汰来源必须完整非空，审计始终写服务端canonical来源；API/服务均覆盖空数组拒绝且无写入。
4. 手机CSS被后出现的基础table/th/td规则覆盖：移动手机规则到基础规则之后，浏览器补每轮明细卡片视口内及table语义断言。

终结独立审查已核对223后端、235前端/17文件、build及e2e类型检查退出0、官方audit零漏洞、最终9项Edge（7.7分钟）、迁移备份恢复、HTTP安全、三份实际流程摘要及代表截图，24关键SHA及43条源码manifest逐项一致，结论PASS、无新增阻断或待修复项。原失败证据和未验证范围保持原状态。[独立核验记录](evidence/event-flow/independent-review.md)。

本轮失败记录包含：首次短QA密钥未通过配置校验；旧业务断言/旧界面标签及新增白名单/单位断言不匹配；测试文件一次缩进错误已修正；npm镜像审计端点404后改用命令级官方源；QA缺cryptography及证书启动失败后使用现有OpenSSL、未新增依赖；直接HTTP测试缺Origin被HTTPS CSRF拒绝，补正确来源头后通过。首次手机截图展开明细出现横向隐藏的大块空白，后改纵向卡片，原截图保留。失败日志/截图/trace留存，原始私有trace和凭据不进入仓库。

## 未验证范围

本轮PostgreSQL、Linux Docker/Caddy/Nginx、GitHub CI、真实Windows首次安装、实际业务库与正式服务器均UNVERIFIED。此前阶段的PASS不替代本轮。未应用0010到业务库，未初始化或改密真实管理员。
