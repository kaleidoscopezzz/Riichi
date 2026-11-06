# 审查问题修复验证报告

日期：2026-11-06（Asia/Shanghai）。状态：Developer 自检 PASS，未提交候选，等待 Owner 验收。

## Git 起点和边界

本地分支 `fix/review-findings`，起点 main `b882ef065bbd9ebae55f6a04ea324675ee41e3fb`（已合并 PR #1 Docker 生产部署），开始时工作区干净。未执行 commit、push、tag、merge；历史迁移、报告、证据与 Tag 均未修改。新增迁移 `tournaments/0005`、`0006`，只加字段；Owner 库升级前须备份、只读核对迁移图后明确确认。

## 修复清单

### 后端

| 编号 | 问题 | 修复 | 测试 |
| --- | --- | --- | --- |
| B1 | 同一并列组可录多份抽签再挑选确认 | 同组、同来源版本仅允许一条待确认记录（409 `lottery_pending`）；新增作废接口，作废人/时间/原因留痕，已作废不能确认，已确认不能作废；迁移0005加字段及 `lottery_void_state` CHECK | `test_lottery_pending_void_and_only_confirmed_ranks`、`test_lottery_void_state_database_constraint`、HTTP 闭环测试 |
| B2 | 确认成绩覆盖录入人与录入时间 | 只确认不带点数时 `edited_by`/`edited_at` 不变 | `test_confirm_only_keeps_draft_editor_audit` |
| B3 | 关键写接口无成功路径测试；0004 无自动化测试 | 补成绩确认、换桌、兼容复核、抽签记录/确认/作废、完赛、workspace 的 HTTP 成功测试；新增 `tests_migrations.LegacyMigrationTests`（内存库从0003迁到最新，比对旧列逐字节不变） | 见左 |
| B4 | historical_only 赛事可经换桌占用新桌 | 409 `historical_only` | `test_historical_only_cannot_take_new_machine` |
| B5 | 释放原因覆盖预留建立原因 | 新列 `release_reason`（迁移0006，已释放旧行复制原 reason，旧列不改） | `test_fault_replacement_reason_survives_completion_release` |
| B6 | 兼容复核缺桌时500 | 409 `legacy_structure_invalid` | `test_review_incomplete_legacy_tables_is_conflict`、`test_http_incomplete_legacy_structure_is_409` |
| B7 | 惰性桥接遇畸形首轮抛400致赛事卡死 | 与0004同一判定，异常进入 review_required，仍桥接 active 分配保护物理池 | `test_bridge_malformed_first_round_written_after_migration` |
| B8 | 非管理员正确密码返回403，可验证密码 | 与密码错误一致返回400 `invalid_credentials` | `test_login_failure_inactive_and_nonstaff`（唯一修改的旧断言） |
| B9 | 错误中间件丢失安全头与 Cookie | 复制原响应头（除 Content-Type/Length）与 Cookie | `test_unknown_api_route_keeps_security_headers` 等 |
| B10 | DRF CSRF 失败返回英文 `permission_denied` 并回显 Origin；404 码为 `request_failed` | `CsrfSessionAuthentication` → `csrf_failed`；Http404 → `not_found` | `test_drf_csrf_failure_matches_django_csrf_failure` 等 |
| B11 | 只含零宽/RTL/控制字符的昵称可保存 | 拒绝 Cc 与 bidi 控制符，须含可见字符，允许 emoji ZWJ；选手昵称与管理员显示名称共用 | `test_invisible_or_control_nicknames_rejected` 等 |
| B12 | search 含 NUL 时 PostgreSQL 500 | 选手/设备/赛事列表含控制字符返回400 | `test_search_with_control_characters_is_400` |
| B13 | 管理员无档案时 `players/me` 500 | 原子惰性建档，User→Profile 锁顺序 | `test_admin_without_profile_gets_lazy_signal_profile` |
| B14 | 赛事详情返回参赛者内部 username | 移除 | `test_participants_never_expose_internal_username` |
| B15 | `verification/http_check.py` 读取已移除字段 | 改按昵称筛选；`uat_fix_01.py` 期望码同步 B8 | 仅语法检查（UNVERIFIED） |
| B16 | 赛事草稿无乐观并发 | 输出只读 `revision`，PATCH/名单 PUT 可选携带，不符409 `stale_tournament`；比较在条件 UPDATE 内完成 | `test_optional_revision_rejects_stale_draft_writes`、并发测试 |

### 前端

| 编号 | 修复 |
| --- | --- |
| F1 | 抽签录入成功即刷新数据；已有待确认记录时只能确认或作废（作废须填原因并二次确认）；已作废记录只读显示；`lottery_pending`/`lottery_voided`/`lottery_conflict`/`tournament_completed`/`stale_standings` 冲突后自动刷新 |
| F2 | 登录后回到原页面（保留 search/hash），`safeReturnPath` 防开放重定向 |
| F3 | `lib/points.ts` 统一解析点数：去首尾空白（含全角）、全角数字与负号归一、严格整数；非法输入在格子处提示并阻止保存 |
| F4 | `displayScore` 不再出现 `−0.00`、负分母与分母0安全处理；新增 ErrorBoundary，渲染异常不再白屏 |
| F5 | `unresolved_groups` 改为可选并加保护 |
| F6 | 嵌套字段错误递归展开，不再出现 `[object Object]` |
| F7 | 首轮选桌预览后修改须重新预览；兼容复核预览展示 A～D 映射、historical_only 及原因 |
| F8 | 选中后续页选手保留已加载结果；已归档选手标签显示“已归档”及提示 |
| F9 | 删除参赛者 `username` 类型；草稿保存携带 `revision`，冲突提示并可重新加载；占用历史分开显示建立原因与释放原因 |

### Windows 启动器与部署

| 编号 | 修复 |
| --- | --- |
| L1 | PID 不存在或创建时间不同即判定原进程已退出，只清理状态、不终止该 PID；子进程同样按 PID+创建时间核对；创建时间相同但路径/命令行不符仍拒绝。无权打开的进程改从内核进程列表读取创建时间 |
| L2 | 原生探测统一经 `Invoke-Probe`（局部 Continue + 退出码），py 无 3.13 时继续尝试 `.tools` 与 PATH，全部失败给中文提示 |
| L3 | 读取状态遇 IO 异常、空内容、JSON 不完整时最多重试20次×50ms，持续损坏才报错 |
| L4 | 端口检测增加对 127.0.0.1 与 ::1 的连接探测 |
| L5 | `run.ps1` 判断子进程存活同时比对创建时间 |
| L6 | `verify_launcher.py` 按实际路径计算中文空格检查；新增不依赖真实安装的 `--self-test`（7项） |
| D1 | HTTP→HTTPS 跳转在 `HTTPS_PORT` 非443时带端口；端口非法拒绝启动 |
| D2 | 备份默认目录改为 `${HOME}/riichi-backups`；显式指向仓库内时警告，`status.sh` 提示旧目录残留备份（不移动不删除） |

### 工程

- 新增 `.github/workflows/ci.yml`：SQLite 与 PostgreSQL 17 后端 check/makemigrations/migrate/全量测试，前端 typecheck/Vitest/build/npm audit，部署脚本 ShellCheck 与 Compose 校验，启动器 PS5.1 解析/BOM/C# 编译。
- 更新 AGENTS.md（当前任务、迁移、抽签规则、PID 判定、CI）、roadmap、requirements、baselines（远端 Tag 只读核对）、F0-06 规范第6/11节。

## API 与行为变更

- 新路由 `POST /api/v1/tournaments/{id}/lotteries/{lottery_id}/void/`，严格请求体 `{"reason": "..."}`（去首尾空白后1～500字），200返回抽签记录；404 `not_found`；409 `tournament_completed`/`lottery_conflict`/`lottery_voided`。
- 抽签记录新增 `voided_by_id`、`voided_at`、`void_reason`；workspace 列出含作废在内的全部记录。
- 预留 history 新增 `release_reason`；`reason` 仅表示建立原因（迁移前已释放行的 reason 保留旧释放原因并复制到新列）。
- Tournament 输出只读 `revision`；PATCH 及名单 PUT 可选 `revision`。参赛者移除 `username`。
- 新409码：`lottery_pending`、`lottery_voided`、`tournament_completed`、`historical_only`、`legacy_structure_invalid`、`stale_tournament`。
- 状态码/错误码变化：非管理员登录403 `admin_required` → 400 `invalid_credentials`；DRF CSRF 失败 → 403 `csrf_failed`；资源不存在 → `not_found`；搜索含控制字符 → 400；管理员无档案 `players/me` 500 → 200；畸形旧赛事进入复核（409 `resource_review_required`）而非永久400；不可见昵称 → 400。
- 只确认不带点数时保留草稿录入人；带点数确认时确认人同时为录入人。

## 实际命令与结果

环境：Windows 11，Windows PowerShell 5.1.22621；Python 3.13.15（项目外隔离虚拟环境，非 backend/.venv）；Node 25.8.0 / npm 11.19.1。

| 命令 | 结果 |
| --- | --- |
| `manage.py check` | PASS，0 issues |
| `manage.py makemigrations --check --dry-run` | PASS，No changes detected |
| 全新 SQLite 库 `manage.py migrate` | PASS，至 tournaments.0006 |
| `manage.py test` | **135 / 135 PASS**（修复前112） |
| `npm run typecheck` | PASS |
| `npx vitest run` | **195 / 195 PASS，14 文件**（修复前94，10文件） |
| `npx vite build` | PASS（JS 505.71 kB，超出 Vite 500 kB 提示阈值，未做拆分） |
| PS5.1 `ParseFile` 4个 ps1、`Add-Type LauncherProcess.cs` | PASS；ps1 均 UTF-8 BOM，bat 均 CRLF |
| `verify_launcher.py --self-test` | PASS，7/7 |
| `bash -n` 全部部署脚本；YAML 解析 compose.yaml 与 ci.yml | PASS |

## UNVERIFIED

- PostgreSQL 实连（B12 原500只能推断；CI 已配置 PG 任务但尚未在 GitHub 上运行）。
- CI 工作流本身尚未推送运行。
- 浏览器实测与深浅主题 320/390/1440px 截图（新 UI 仅有 DOM 测试）。
- `verify_launcher.py` 完整 QA 模式（需真实首次安装）、真实 Windows 首次安装。
- ShellCheck、`docker compose config`、nginx 实际跳转、跨端口浏览器 CSRF、Linux 备份权限及真实服务器部署。
- `verification/http_check.py`、`uat_fix_01.py` 仅语法检查。

## 待 Owner 决定

1. 抽签“同组仅一条待确认、录错须作废留痕”是对规范第6节的补充，已在规范中标注待确认。
2. HSTS 默认 0（Docker 分支既有策略），本轮未改。
3. Tag `baseline/F0-06` 指向 UAT 整改前的 `b9e83bb`，与文档旧表述不一致，含义待确认。

## 后续追记：PR #2合并与生产任务（2026-11-06）

上文是审查修复轮当时的自检、未提交状态与未验证项，原文保留。PR #2现已合并，生产任务开始时本地/远程main均为`34d4cbdea89bba81a503f2b476f2e1d69de5d714`；GitHub状态不再是未提交候选。Owner在当前项目约束中已明确确认同组单条待确认及作废留痕规则，规范同步其状态。新候选的CI/PostgreSQL/浏览器/真实服务器证据只记录在[生产上线验证](production-launch-verification.md)，不反写为旧轮已执行。
