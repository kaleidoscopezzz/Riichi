# 自定义分桌策略与高分桌附加基础分

本轮Owner已确认：新赛事创建/草稿中选定策略，启动后固定；提供手动、完全随机、高高碰、瑞士轮；瑞士轮“避重优先”和“积分接近优先”两种都可选。高高碰按A～D桌配置每位选手的固定非负附加积分，原开局/返还点数不变。高高碰首轮仍随机且不加桌附加分，后续分档轮次应用配置。手动模式在每轮生成前拖拽分桌，已生成轮次保留。

当前实现中首轮随机、后续原有高高碰排序的事实已向Owner说明。本轮从前轮更正工作区创建`codex/pairing-strategies`；Owner随后已提交并合并前轮更正PR #4，当前HEAD为`efd5a21`，本轮分桌改动仍独立未提交。原验证记录和失败证据保留，不清理工作区或Owner数据库。

瑞士轮目标明确为：组内6对选手的历史相遇次数总和与积分绝对差总和，按选择的优先级做词典序最小化。精确Fraction积分以公共分母缩放成整数，4人分组DP枚举并记忆化；同成本按已记录随机种子顺序稳定选择，不用账号ID决胜。UI另显示发生重遇的不同对数，不能把“不同对数”误称为优化目标。

## 实现与兼容

- 新赛事保存分桌策略及A～D附加分，启动后通过原有赛事父行锁冻结。历史赛事赋`legacy_v1`/`none`/零值，不自动升级或重新计算旧分数。
- 每轮预览只读，以冻结名单、同一批确认成绩和历史座次规划分组。签名计划绑定当前管理员/赛事/轮次/revision/完整成绩版本/规则/首轮随机序列，30分钟有效；生成时原子校验，失效不自动重试。
- 自动策略按签名分组生成；手动模式通过PointerEvents或统一Select交换，服务端要求每桌4人、名单完整/唯一/本赛事。四风生成时随机；已生成轮次、物理映射和ID保持。
- `add_table_base_bonus_v1`为独立计分组件，原Uma/Oka基础策略版本1/2保留含义。轮桌保存冻结base_bonus和来源，试算、确认、更正、累计和冠军均读同一值，原始总点数校验不变。
- 新增0009仅加字段/约束，旧行与新对象默认值分开；0001～0008不改。008演练固定在其原目标，009有单独原字段及旧结果/更正/身份比对。

## 本轮实际验证

Windows PowerShell7.6.9；Python3.13.15/Django5.2.18/SQLite3.53.1；项目内Node22.23.4/npm11.19.1；Playwright1.65.0调用已安装Edge。QA SECRET_KEY/账号为本轮新生成，关闭dotenv加载，所有库、备份、证书、凭据、缓存和trace在忽略目录，未连接正式服务器。

| 项目 | 实际命令/范围 | 结果 |
| --- | --- | --- |
| Django系统及迁移 | backend `manage.py check`、`makemigrations --check --dry-run`、`migrate --noinput`，独立QA库 | PASS；0009正常应用，无遗漏迁移 |
| 后端全量 | `manage.py test --noinput` | PASS，193项，51.108秒 |
| 新分桌/旧迁移专项 | `manage.py test tournaments.tests_pairing tournaments.tests_migrations --noinput` | PASS，18项，含精确DP/两优先级/16人性能/签名/旧原字段/bonus更正及完赛 |
| 前端全量 | `npm run typecheck`、`npm test` | PASS；16文件、220项，含重新预览乱序/卸载取消 |
| 构建/依赖 | `npm run build`、`npm audit --audit-level=high --registry=https://registry.npmjs.org --cache .cache/npm` | PASS，0漏洞；保留单JS块超过500kB构建提示 |
| 备份恢复 | `.verification/pairing-strategies/check_migration.py`调用[迁移演练](../../backend/verification/pairing_migration_check.py) | PASS，原列/结果/更正/ID及旧规则快照不变；备份完整、独立恢复后升级、幂等重跑通过 |
| 新策略浏览器 | `npm run test:e2e -- --config=../.verification/pairing-strategies/playwright.local.config.ts e2e/pairing-strategies.spec.ts` | 五预设完整8人2轮PASS，含鼠标分桌、瑞士4/6对重遇差异、A+5/B+2权威分数及完赛 |
| 手机触屏专项 | 同上`--grep=sixteen`，独立输出`browser-mobile-second` | PASS，36.1秒；390/320同一单指A→原视口外D，生成分组与拖拽一致，16人1轮完赛 |
| 浏览器完整回归 | 同上，输出`browser-full`，全部五个E2E用例 | 5用例PASS，5.5分钟；包含原Oka、成绩更正与16人6轮，手机专项35.9秒 |
| 独立Reviewer | `/root/score_corrections_reviewer` | 最终源码/实测/失败记录/迁移/截图复核PASS，无待修复项；两P2已解决 |
| 范围/秘密/忽略 | git diff/旧迁移与锁/已生成QA秘密扫描 | PASS，最终63个候选文件范围无QA密码/私钥，历史迁移和锁未改 |

原始日志位于`backend/.verification/pairing-strategies/`，可分享版本及实际截图存入[evidence/pairing-strategies](evidence/pairing-strategies)。当前本机HTTPS由临时TLS静态/API代理访问隔离Django/SQLite，使用私有本机证书和独立浏览器上下文；不冒称Caddy/Nginx/PostgreSQL或正式证书验证。QA服务已按本实例标记正常停止，18089/18449无残留监听。

主要证据：[后端193](evidence/pairing-strategies/backend-full-first.log)、[前端220](evidence/pairing-strategies/frontend-full-first.log)、[最终五用例浏览器](evidence/pairing-strategies/browser-full.log)、[迁移/备份恢复](evidence/pairing-strategies/migration-summary.json)。界面：[手动桌面](evidence/pairing-strategies/manual-mouse-desktop.png)、[高高碰附加分](evidence/pairing-strategies/ranked-round2.png)、[瑞士避重](evidence/pairing-strategies/swiss-repeats-round2.png)、[320触屏跨桌](evidence/pairing-strategies/manual-touch-320.png)。实际桌面/手机图片已人工查看，未以jsdom冒充视觉验收。

## 审查与保留的失败

独立审查发现两P2：重新预览原来另开未受Abort/当前轮次保护的请求，迟到会覆盖新轮；触屏长列表没有边缘自动滚动。现已统一初始/重试effect和目标键，并补重试迟到/卸载取消回归；拖动使用实际Sheet滚动容器的RAF边缘滚动，重命中目标，所有取消/忙碌/失capture/卸载均清理。源码复核PASS，触屏实测另记录。

- 初次旧008迁移专项的一项失败：该历史演练原来迁移到所有最新叶子，0009出现后不再满足“008不加旧列”的有效断言。现固定008演练目标，保留原断言和失败日志，0009另行核验。
- 首次手机E2E失败：单指已经滚到D桌，但持续自动滚动将D首行越过原采样区域；保留截图/日志。用同一触摸从边缘移到中央停止滚动，必要时从上边缘把目标带回视口，再落位；没有DOM强制滚动/伪造拖拽结果，手机36.1秒复验通过。
- 原有历史报告、Tag、失败证据均保留；新策略并不改变以往验收结论。

## 未验证/停止范围

正式业务库/服务器、PostgreSQL本轮、Linux Docker/Caddy/Nginx与GitHub CI均**UNVERIFIED**；不沿用历史PASS。新迁移尚未应用到业务库。本轮仍为本地工作分支未提交/推送/合并或部署；Owner已独立完成前轮更正PR4，不视为本轮新策略交付。
