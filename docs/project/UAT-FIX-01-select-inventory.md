# UAT-FIX-01 全站下拉使用清单

Owner 追加验收项，2026-11-04；属于当前未封版候选，无新阶段。扫描范围为全部 `frontend/src/`，原始匹配见 [整改前扫描](evidence/UAT-FIX-01/select/native-before.txt)，最终扫描及文件审计见 [本次审计](evidence/UAT-FIX-01/select/audit.json)。

原有 **7 个业务文件、9 处 `<select>`**（动态生成 `<option>`），全部迁移为唯一 `components/ui/select.tsx`。未新增依赖或锁文件变化。

| 文件 | 原生位置/业务 | 统一 Select 输入与保留行为 |
| --- | --- | --- |
| `pages/tournaments.tsx` | 赛事状态筛选 | 空/草稿/已启动/已完赛；原 status 查询参数及翻页重置 |
| `pages/machines.tsx` | 麻将机状态筛选 | 空/可用/维护/停用/退役；原 status 查询参数 |
| `pages/players.tsx` | 选手状态筛选 | active/archived/空；原有效/归档/API与分页 |
| `components/machine-editor.tsx` | 设备状态 | available/maintenance/disabled；busy/readOnly禁用，退役仍只读 |
| `components/tournament-editor.tsx` | 总轮数 | 1～6；原草稿摘要、保存输入与冻结约束 |
| `pages/rounds.tsx` | 查看轮次 | 真实已有轮次，Number转换与只读结果切换 |
| `components/competition-action.tsx` | 首轮物理桌选择；同一pickers复用于旧赛事兼容复核 | 空值/真实machineId，跨桌重复项禁用、预览/确认与API数组保持 |
| 同上 | 故障替换目标物理桌 | 仅assignable候选、空值；修改后重置预览，仍须原因与二次确认 |
| 同上 | 公开抽签完整顺序 | 真实participantId、跨顺位重复项禁用；保存后锁定、原完整性校验 |

全站状态、选桌、轮次及抽签不再直接输出原生选项列表。Radix为HTML表单语义在组件内部生成 `select[aria-hidden=true][tabindex=-1]` 桥接，仅用于值同步/required/FormData；实际触发器为 button/combobox，展开为Portal中的listbox/option，没有可交互原生菜单。不得将桥接误判为业务遗漏并删除。

统一组件接受 `value / onValueChange / options / disabled / required / name / aria-label` 等。空字符串在Radix Item的内部边界映射后仍回传空字符串，内部占位值不传给业务API；数字ID按原调用处转回Number。每个调用处均保留显式可访问名称。

自动测试原 `user.selectOptions` 改为实际点击 combobox/option，原请求参数/字段断言保留；测试辅助集中在 `src/test/`，jsdom指针/scrollIntoView兼容仅作用于测试，不修改运行时。
