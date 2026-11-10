# 开发路线

D0-01已CLOSED / PASS；F0-06候选已通过Planner源码/证据审查，此后UAT-FIX-01、Windows启动器、选手联想、Docker生产部署（PR #1）和审查修复/CI（PR #2）已合入main（`34d4cbdea89bba81a503f2b476f2e1d69de5d714`）。当前为Linux生产上线阶段，见[执行计划](project/production-launch-plan.md)与[实际验证](project/production-launch-verification.md)。远端Tag `baseline/F0-06`指向UAT整改前`b9e83bb`，保留历史含义待Owner确认，不以本轮上线重打Tag或改判验收。详细业务规则只在[F0-06完整功能规范](F0-06-functional-spec.md)维护。

| 阶段 | 范围 | 当前状态 |
| --- | --- | --- |
| F0-01 工程骨架 | 健康API、前后端工程、布局、设计基础、测试及文档 | **CLOSED / PASS**；baseline/F0-01，94a1fec747806682602dd24f7edbbcc4e27d07f0 |
| F0-02 账号与选手 | 注册、Session、CSRF、本人资料、管理员选手列表 | **CLOSED / PASS**；baseline/F0-02，59be947ca133dbe18a63dcdc99e55a3243daed51 |
| F0-03 设备台账 | 四台现役容量、状态、退役与历史 | **CLOSED / PASS**；baseline/F0-03，0d7e96b0b920e490abbf7acd1d4aba38493025f9 |
| F0-04 赛事领域 | 草稿、独立配置、参赛名单、启动冻结 | **CLOSED / PASS**；baseline/F0-04，434a8aa9ae5bd075705322e0556688b7424db16a |
| F0-05 首轮与资源 | 首轮随机、轮次级设备分配/调整/释放、并发和历史 | **CLOSED / PASS**；baseline/F0-05，41929da1e53f8bb481beb4ea3bc31b65f9ee86ff |
| D0-01 开发前文档统一 | 最终需求、两个已解决决胜规则、固定选桌与兼容设计、完整验收 | **CLOSED / PASS**；文档Commit `5f31891b4ae3a589057e7054758abb08ca42ec72`，Owner确认已推送及双端核验 |
| F0-06 完整比赛闭环 | 成绩草稿/确认→精确计分→累计榜→后续分桌→冠军决胜/公开抽签→完赛及自动释放；同时完成赛事级选桌及非破坏性兼容 | **Planner源码/证据审查通过**；UAT-FIX-01已合入main（`checkpoint/UAT-FIX-01`，`c9d7bb8`）。远端Tag `baseline/F0-06`指向`b9e83bb`（2026-11-04 14:09，说明“approved”），是否作为正式基线待Owner确认；V1.0最后一次核心功能开发，不拆F0-07/F0-08 |
| 集成测试与部署验收 | 全流程/迁移/并发验证、PostgreSQL验证、安全加固、部署与发布验收 | Linux Docker Compose生产部署已合入main（PR #1，`b882ef0`），容器内PostgreSQL全量测试通过；真实Ubuntu服务器与公网HTTPS仍UNVERIFIED。CI已建立（`.github/workflows/ci.yml`） |
| 审查问题修复 | 代码审查发现的抽签、审计、兼容边界、认证/错误码、输入校验、前端交互、启动器与部署问题 | **PR #2已合并**，main `34d4cbd`；历史[修复报告](project/review-findings-fix-verification.md)保留当时测试快照；新增迁移tournaments/0005、0006 |
| Linux生产上线第一阶段 | Caddy 自动 HTTPS 工程、代理信任、迁移/恢复保护和浏览器 QA | 隔离验证通过。合并与 CI 状态见 [PR #3](https://github.com/kaleidoscopezzz/Riichi/pull/3) 和[验证报告](project/production-launch-verification.md) |
| Linux生产上线第二阶段 | 新服务器盘点、正式main部署、真实CA/续期、线上管理员登录及运维验收 | **未授权执行**，等待Owner新服务器；不得连接旧或任何正式服务器，未实测项保持UNVERIFIED |
| 团队赛 T0～T4 | 可配置队伍/成员、每桌每队一人，自由场次与固定位置循环，精确团队积分汇总及团队冠军 | Owner已授权实现且确认TEAM-01～13；独立实现候选及隔离QA，规则见[团队赛规划](team-tournament-plan.md)，实际结果见[团队赛验证](project/team-tournaments-verification.md)，未正式验收/未上线 |
| 未来版本候选 | 微信及其他赛制扩展 | 不纳入V1.0，须另行立项 |

团队赛T0～T4属于Owner本轮独立功能授权，工作分支`codex/team-tournaments`，基线main `8f94f2e`；不属于生产上线第二阶段授权。未验证的PostgreSQL、Owner库及生产环境保持UNVERIFIED，不用功能自检改判历史F0-06验收。

## F0-06启动门禁与停止点（历史阶段记录）

1. Planner审查D0-01最终文档一致性；五项业务决策已确认，见规范OP-01～OP-05 RESOLVED，不再作为待决事项。
2. Owner手动建立文档Commit并推送GitHub，记录完整SHA。
3. 核验远程文档与本地批准版本内容一致，再由Planner下发F0-06完整开发任务。

以上门禁由Owner本次任务确认完成，HEAD已核验为批准文档Commit。F0-06开发者不commit、tag、push；提交候选和证据后立即停止，等待Planner独立验收。F0-06必须覆盖4人1轮、8/12人多轮、16人6轮及全部确认/冠军/资源闭环，不能只交成绩后把剩余功能另拆阶段。

TBD-001与TBD-002均为RESOLVED。后续分桌按累计分、第一/第二次数、逆序逐轮积分、首轮持久化随机顺序处理，新轮四风重新随机；冠军全同仍公开抽签，不能使用首轮兜底。终局点数允许负数与零、总和强校验、精确有理数权威计算/无损存储、旧有效占用继承及异常复核、冲突旧断言可调整均已确认，详细规则只在统一规范维护。保留F0-01～05 CLOSED / PASS及全部原报告/证据，不以目标改写历史事实。

F0-06候选完整闭环与验证记录见[交付报告](project/F0-06-verification.md)，不将Developer自检标为正式CLOSED / PASS。

UAT-FIX-01属于F0-06人工验收整改：列表/操作区对齐、老板维护选手、关闭公开注册及安全admin交互初始化；不新增核心阶段。Owner提交修复候选→Planner复核→Owner再次人工验收通过，才建立baseline/F0-06。见[整改报告](project/UAT-FIX-01-verification.md)。
