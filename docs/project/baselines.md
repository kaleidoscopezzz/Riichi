# 本地与 GitHub 双基线制度

## 当前正式基线

根据 Owner 下发的 F0-02 任务，F0-01 已正式验收：Tag `baseline/F0-01`，Commit `94a1fec747806682602dd24f7edbbcc4e27d07f0`。本地已用 `git rev-parse baseline/F0-01^{commit}` 验证 Tag 解引用指向该 Commit（附注 Tag 对象 SHA 与 Commit SHA 不同是正常现象）。

F0-02 已正式验收：Tag `baseline/F0-02`，Commit `59be947ca133dbe18a63dcdc99e55a3243daed51`，分支main。Owner在F0-03任务中确认该正式基线；本地Tag解引用与HEAD已核实一致。历史F0-02报告中的“未提交、待验收”是当时快照，不表示当前状态。

F0-03 已正式验收：Tag `baseline/F0-03`，Commit `0d7e96b0b920e490abbf7acd1d4aba38493025f9`，Branch `main`，Planner：**PASS**。本次 F0-04 开始时已用本地 Tag 解引用和 HEAD 核实；该验收状态由 Owner 本次任务确认，旧报告保留原历史快照。

F0-04：当前实施中，正式基线尚未建立。开发及自检完成后等待 Planner 源码审查；本阶段不 commit、tag 或 push。所有后续 Git 提交与标签由 Owner 手动执行；不得修改或删除已有基线。未通过本次任务重新核验 GitHub 远程引用，不把本地核验冒称远端双基线核验。

## F0-01 候选提交历史

2026-11-03：Planner 已单独授权首次 Git 候选提交并推送至 `origin/main`，用于 GitHub 源码审查。本次不创建 Tag；此处为候选提交时状态；后续 Owner/Planner 已建立下述正式基线。见 [候选提交记录](F0-01-candidate-submission.md)。

## 骨架实现结束时记录（历史快照）

| 项目 | 状态 |
| --- | --- |
| 本地工程基线 | **尚未建立** |
| GitHub 工程基线 | **尚未建立** |
| 本地分支 | `main`，尚无 Commit |
| origin | `https://github.com/kaleidoscopezzz/Riichi.git` |
| 当前任务 | F0-01 工程骨架实现与验证；等待 Planner 验收 |
| Commit / Tag | 无 |

本文记录基线管理制度，不因本地测试通过而自动建立基线。骨架实现阶段禁止 commit、tag、push；上述单独授权仅允许本次候选 commit/push，不授权 Tag 或最终基线验收。

## 建立条件与顺序

1. Developer 完成约定工程实现和实际验证，提交变更清单、环境、命令、结果、失败/未验证项及风险。
2. Planner 外部审查并验收当前候选。自检通过不能替代 Planner 验收。
3. Planner 另行下发首次基线任务，明确授权提交、标签（如需要）与同步范围。
4. 在该任务中建立本地 Commit，记录完整 Commit SHA、任务编号、验收结论、证据位置和依赖锁。
5. 经授权同步 GitHub，确认远端引用指向同一 Commit SHA，再登记 GitHub 基线。

本地与 GitHub 是同一已验收候选的两个位置。仅本地保存、仅本地测试或未确认远端 SHA 时，不得称为双基线已建立；同步失败应保留本地状态并记录原因，不修改远程配置或重写历史。

## 后续基线记录字段

每次基线记录至少包含：任务编号、基线日期（Asia/Shanghai）、范围、完整 Commit SHA、分支、可选标签、Planner 验收结论与时间、实际验证证据、远端确认结果，以及已知限制。

依赖锁、源代码或配置变更后，旧验证只证明旧候选。建立新基线前应针对实际候选重新完成受影响检查。密钥、`.env`、本地数据库、虚拟环境、依赖目录和构建缓存均不得纳入基线。
