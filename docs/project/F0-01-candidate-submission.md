# F0-01 首次候选提交

日期：2026-11-03（Asia/Shanghai）。本次仅按 Planner 单独授权提交和推送 F0-01 候选，供 GitHub 源码审查；不代表最终基线已验收，不创建 Tag，不修改架构或新增业务。

## 授权与候选

本次授权对骨架实现阶段禁止 commit/push 的约束构成一次明确例外，仅允许首次提交至 `origin/main`。禁止强制推送、历史重写及继续下一阶段。

- 仓库：`D:\Riichi`，分支 `main`。
- origin：`https://github.com/kaleidoscopezzz/Riichi.git`。
- 提交前已确认本地无 Commit，远程 `main` 不存在。
- Commit Message：`chore(scaffold): initialize Riichi foundation`。
- 本候选的完整 SHA 以 Git 提交对象为准：`git rev-parse HEAD`；远程用 `git ls-remote --heads origin main` 核对。提交后核验结果在任务最终报告中提供，避免在提交内容中循环写入自身 SHA。
- [实际提交文件清单](evidence/f0-01-candidate/committed-files.txt)。

## 本次实际复验

后端工作目录 `D:\Riichi\backend`：

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test common config -v 2
.\.venv\Scripts\python.exe -m pip check
```

结果：系统检查 0 问题，测试 15/15 通过，依赖一致性通过。

前端工作目录 `D:\Riichi\frontend`：

```powershell
npm run test
npm run build
```

结果：测试 8/8 通过，构建内的应用与工具配置 TypeScript 检查通过，Vite 生产构建通过。没有更改源码或依赖锁；68 项源码/原文档与上次自检 SHA-256 一致。本次仅增补提交记录和复验日志，更新基线文档以区分历史快照与候选状态。

原始日志位于 [evidence/f0-01-candidate/](evidence/f0-01-candidate/)。原 [F0-01 骨架自检报告](F0-01-verification.md) 及其文件清单、Git 状态、哈希与失败证据均保留为当时快照，不表示提交后的 Git 状态。

## 文件与敏感信息检查

检查全部 Git 可见文件及排除规则，不提交 `.env`、真实密钥、数据库及 sidecar、虚拟环境、运行时、node_modules、下载缓存或构建产物。保留源码、测试、依赖锁、工程文档、上游许可和验证证据。

定向扫描包含私钥、常见 Token、明文密码/密钥赋值和含凭据 URL；首次命中 `.env.example` 的 `USERNAME:PASSWORD@HOST`，人工核对确认是占位示例，仅对这一精确示例排除误报，没有发现真实敏感信息。日志不输出真实本地 `.env` 内容。该扫描不构成穷尽所有敏感信息格式的保证。

## 后续边界

候选提交推送成功后，核对本地/远程完整 SHA 和干净工作区并停止。Planner 进行 GitHub 源码审查及最终基线验收；Developer 不自行宣布正式基线通过。PostgreSQL 实连与生产部署仍未验证，业务功能仍保持 F0-01 约定边界。
