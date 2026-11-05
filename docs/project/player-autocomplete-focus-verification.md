# 选手联想与搜索焦点修复验证报告

日期：2026-11-05（Asia/Shanghai）。状态：Developer 自检 PASS，未提交候选，等待 Owner 验收。

## Git 起点和边界

开始时 `git status --short` 为空。Owner 已准备指定分支 `bugfix/player-autocomplete-focus`，其 HEAD、fetch 后的 origin/main 和 `git ls-remote origin refs/heads/main` 均为 `49febeb9b72dab8ebcc883bfbb8cdba62bedc0e8`，因此直接沿用，无需重复创建或切换 main。交付时再次只读核对远程 main，SHA 未变。

未执行 commit、push、tag、merge；未修改后端源码、API、数据库模型、迁移、计分、分桌、冻结规则、启动器或依赖声明/锁文件。历史报告与证据保留。

## 修改文件

| 文件 | 修改目的 |
| --- | --- |
| [player-picker.tsx](../../frontend/src/components/player-picker.tsx) | 提取赛事选手多选联想控件，复用现有 Radix Popover 和有效选手 API |
| [tournament-editor.tsx](../../frontend/src/components/tournament-editor.tsx) | 引入新控件，移除旧手动搜索/翻页列表；原保存、关闭及草稿初值逻辑不变 |
| [globals.css](../../frontend/src/styles/globals.css) | 限定搜索容器内部 input 无独立描边，外层保留金色 focus-within；菜单、长昵称和标签换行样式，移除失用 picker-results 样式 |
| [player-picker.test.tsx](../../frontend/src/components/player-picker.test.tsx) | 新增 8 项交互测试 |
| [tournaments.test.tsx](../../frontend/src/pages/tournaments.test.tsx) | 原有赛事集成测试适配联想、加载更多和带 ID 的移除标签 |
| [AGENTS.md](../../AGENTS.md) | 更新当前任务/分支，明确单选 Select 与多选联想控件的复用边界 |
| 本报告及 [evidence/player-autocomplete-focus](evidence/player-autocomplete-focus/) | 本轮实际命令输出、HTTP 结果、截图、几何/样式检查及文件审计 |

完整文件清单见 [change-manifest.txt](evidence/player-autocomplete-focus/change-manifest.txt)。

## 实现与契约

- 继续使用 `GET /api/v1/players/?page=1&search=关键词&eligible=true`。后端原有昵称 icontains、20 人分页、有效选手及排除管理员规则未改；仍由后端最终检查参赛资格。
- 聚焦立即展开并查询；非空输入 250ms 防抖，中文 composition 期间暂停查询/选择。组合结束后才查询；Enter 不提交外围赛事表单。
- 每次查询变化、关闭、禁用及卸载均清除定时器并 abort。effect 有独立 current 标志，忽略不遵守 AbortSignal 的旧响应，避免乱序覆盖和卸载更新。
- 首次/新关键词从第一页开始；“加载更多选手”追加后续页，按 ID 去重。后续页失败保留此前结果，重试原页。
- 只展示昵称、稳定选手 ID 和已选状态。按 player_id 维护名单；选中项不可重复添加，移除使用标签。最多 16 人并明确提示；选中后清空关键词并保持输入焦点。
- 新控件只更新父组件的本地名单。保存仍由原 saveTournament 一次提交 participant_ids、配置及赛事 ID，不自动保存、启动或改变昵称快照。
- Radix Popover Portal/Popper 管理弹层和视口避让，持续跟踪位置，不受 Sheet 滚动容器裁切；选项滚动、换行、深浅主题沿用现有 tokens。
- input 使用 combobox、listbox 多选、aria-selected/disabled、aria-activedescendant 和说明；方向键移动、Enter 选择、Escape 关闭联想而保留 Sheet，Tab 可离开。候选项鼠标按下不夺取输入焦点；选择、加载更多及错误重试恢复输入焦点。

## 搜索框全面排查

实际使用位置（`rg` 扫描 frontend/src 的 machine-search/player-search；未发现其他共享搜索实现）：

| 页面/组件 | 位置 | 处理与证据 |
| --- | --- | --- |
| 赛事管理 | pages/tournaments.tsx | 共享 machine-search；18 组其他搜索焦点检查之一 |
| 选手管理 | pages/players.tsx | 同上 |
| 麻将机管理 | pages/machines.tsx | 同上 |
| 赛事创建/编辑选手 | components/player-picker.tsx（原 tournament-editor.tsx） | account-form 内部专门提高选择器优先级，消除原双层描边 |

只对 `.machine-search input`（及其 account-form 上下文）取消内部 outline/border/box-shadow；容器保留 2px 金色 focus-within。没有全局关闭 input 的 focus-visible；其他表单字段仍保留原焦点规则。

真实 Chrome DOM 计算结果：全部受查搜索内部 border=0px、outline-style=none；外层金色 solid 2px。详见 [browser-metrics.json](evidence/player-autocomplete-focus/browser-metrics.json)。浏览器可能报告 outline-width=3px 但 outline-style=none，该宽度不绘制可见描边，审计以样式及截图共同判断。

## 实际命令与结果

仅用本项目已有运行时、虚拟环境和 node_modules；无新依赖。

| 工作目录与命令 | 实际结果 |
| --- | --- |
| backend：`.venv/Scripts/python.exe manage.py check` | PASS，0 issues |
| 独立 QA 库：Django `call_command('migrate', verbosity=0)` | PASS，新建 QA 库完成现有迁移；非 Owner 库 |
| backend：`.venv/Scripts/python.exe manage.py migrate --check` | PASS，无待执行迁移 |
| backend：`.venv/Scripts/python.exe manage.py makemigrations --check --dry-run` | PASS，No changes detected |
| backend：`.venv/Scripts/python.exe manage.py test` | PASS，108 tests / OK |
| frontend：`npm.cmd test` | 最终 PASS，10 files / 94 tests（原 86 项 + 新 8 项） |
| frontend：`npm.cmd run build`（内含 `npm run typecheck`） | 最终 PASS，两个 tsc 检查及 Vite production build 成功 |
| frontend：`npm.cmd audit --json` | PASS，0 vulnerabilities；仅记录，不改依赖 |
| 仓库：`git diff --check` | PASS，无空白错误 |
| 仓库：`git check-ignore` | PASS，QA 配置/凭据/库、Owner .env/库、node_modules/dist 均被忽略 |

最终输出见 `frontend-tests-delivery.txt`、`frontend-build-delivery.txt`、`backend-tests-full.txt`、`backend-check.txt`、`backend-migrations.txt`、`backend-migrate-check.txt` 和 `npm-audit.json`。早期与中间验证输出保留，不覆盖历史证据。

新测试覆盖防抖 249/250ms 边界、快速输入、AbortSignal、忽略乱序与卸载后返回、中文组合输入、方向键/Enter/Escape/Tab、ARIA 活动项、焦点恢复、禁用、草稿昵称保留、同名不同 ID、不展示内部用户名、重复点击、4/8/12/16 人、满员/移除、分页追加去重、归档过滤、首屏与后续页失败/重试、空状态、内外点击和 Sheet 内保存契约。原赛事校验、编辑、冻结及权限测试继续执行。

旧断言仅按授权交互调整：不再点击“查找选手”，下一页替换为追加加载；重复点击已选候选不取消选择，移除改走带 ID 的标签。原业务提交 participant_ids 断言保留，未删除测试。

## 真实 HTTP 与浏览器

隔离环境：QA 后端 `127.0.0.1:8028`（runserver --noreload），Vite `127.0.0.1:5188`，API_PROXY_TARGET 指向该后端；独立数据库位于忽略目录 `.verification/player-autocomplete/qa.sqlite3`。QA 管理员使用本轮生成的随机凭据，不使用 Owner 密码，不进入截图/本报告。所有截图中的“联想验证”选手与赛事为独立 QA 夹具，来自真实 Django API，不是产品演示数据或硬编码前端数据。

实际 HTTP：26 名有效普通选手，第一页 20、第二页 6；搜索“明”返回王小明 #4、小明 #3、小明 #2；归档小明与管理员未返回，DTO 不含 username，健康检查正常（匿名访问由后端回归测试覆盖）。见 [http-check.json](evidence/player-autocomplete-focus/http-check.json)。

Chrome 实际验证：聚焦展开、昵称自动查询、第二页、同名 ID、鼠标及方向键/Enter 连续选至 4/8/12/16、满员提示、移除再选、搜索词清空、输入焦点保持；保存 16 人草稿后再次编辑恢复名单，临时移除后关闭未保存表单，再开仍为 16 人。数据库只读复核也确认 16 个唯一 player_id，两个同名选手 #2/#3 均保留，见 [draft-persistence.json](evidence/player-autocomplete-focus/draft-persistence.json)。没有启动赛事。单个 Escape 收起联想不关闭编辑 Sheet。

通过停止本轮隔离 QA 后端模拟真实连接失败，菜单展示查询错误与重试按钮；恢复同一 QA 后端后重试查询成功，并继续搜索到真实候选。未切断 Owner 服务或系统网络。空结果与 66 字符长昵称换行也实际验证。

| 视口 | 深色展开截图 | 浅色展开截图 |
| --- | --- | --- |
| 1440×1000 | [1440-dark-open.jpg](evidence/player-autocomplete-focus/1440-dark-open.jpg) | [1440-light-open.jpg](evidence/player-autocomplete-focus/1440-light-open.jpg) |
| 390×844 | [390-dark-open.jpg](evidence/player-autocomplete-focus/390-dark-open.jpg) | [390-light-open.jpg](evidence/player-autocomplete-focus/390-light-open.jpg) |
| 320×800 | [320-dark-open.jpg](evidence/player-autocomplete-focus/320-dark-open.jpg) | [320-light-open.jpg](evidence/player-autocomplete-focus/320-light-open.jpg) |

三种列表搜索框另有 18 张深浅主题/尺寸焦点截图；菜单滚动区域 scrollHeight > clientHeight，Portal 位于 Sheet 外、边界处自动向上翻转。所有记录均无横向溢出，菜单矩形在视口内。其他证据包括 `320-dark-long-name.jpg`、`320-dark-full.jpg`、`empty-result.jpg`、`network-error-320-dark.jpg`、`network-retry-recovered.jpg`、`saved-draft-16.jpg`。完整路径见文件清单。

## 异常与验证限制

- 初次 typecheck 发现提取旧组件后有未清理 useEffect 及缺少 X 图标 import，已修正；最终两次完整 build/typecheck 通过。
- 第一次在仓库根目录直接执行 backend/manage.py test 得到 0 tests，不记为通过。原输出保留 `backend-tests.txt`；改在 backend 目录执行后真实运行 108 项并通过。
- HTTP 验证脚本最初误把原健康检查当作 data envelope，读取报 KeyError；按已有健康检查直接 JSON 契约修正验证脚本后通过，产品接口未改。
- Chrome 自动操作在 Sheet 动画及新候选布局尚未稳定时出现过一次点击未选中/初次表单关闭；重新观察稳定 DOM 与画面后进行语义点击，实际重复操作通过，未以失败动作宣称成功。
- Vitest 的 Node 输出有 localStorage experimental warning；94 项测试全部执行通过。未修改全局运行时规避提示。
- **UNVERIFIED**：真实手机触摸与软键盘、Windows 物理中文输入法组合、读屏软件、Safari/Firefox、PostgreSQL/生产部署。中文 IME 组合事件和取消保护由 jsdom 自动化覆盖；手机截图来自 Chrome 视口模拟，不冒称真机通过。

## 数据保护、审计与停止

Owner `backend/db.sqlite3` 开始与结束 SHA256 均为 `C4738A1EADA032C19A2F9E33F2DCB555A961F1457321B5BD2EBCCD92FFA3A2C9`。没有读取或修改 Owner 管理员密码，未在 Owner 库执行 migrate 或写入。独立 QA 环境、运行凭据和数据库均被 Git 忽略；报告不含 Cookie、CSRF、密码或运行密钥。

本轮 QA 浏览器标签已关闭，临时视口已复原；只停止本轮 QA 端口对应且命令行已核验的进程，不操作 Owner 8000/5173 服务。Git 状态为授权分支内未提交源码/文档/证据，HEAD/远程 main 不变。最终审计见 [audit.json](evidence/player-autocomplete-focus/audit.json) 与 [git-status.txt](evidence/player-autocomplete-focus/git-status.txt)。

结论：本次范围 Developer 自检 PASS；真实环境/外部验收限制如上。停止开发，等待 Owner 点击验收和自行 Git 操作。
