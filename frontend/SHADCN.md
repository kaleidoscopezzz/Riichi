# shadcn/ui 来源记录

基础 UI 文件通过官方 CLI `shadcn@4.23.0` 生成，使用 `new-york`、Radix UI、Tailwind v4。执行命令：

```powershell
npx --no-install shadcn add button card badge separator sheet breadcrumb skeleton -y
```

官方源：https://ui.shadcn.com/docs/installation/vite

生成后统一将 CLI 的 `cn` 包导入改为项目内 `@/lib/utils`（`clsx` + `tailwind-merge`），避免重复工具。组件保留在 `src/components/ui/`，主题与产品组合样式位于 `src/styles/globals.css`。

CLI 仅用于生成，不是应用运行或构建依赖。生成后移除 CLI；其依赖链首次 audit 曾报告 2 low / 4 moderate，移除后重新 audit 验证。后续新增组件时需固定 CLI 版本、审查生成差异并更新锁文件。

配置见 `components.json`。上游许可：MIT（https://github.com/shadcn-ui/ui/blob/main/LICENSE.md）。
