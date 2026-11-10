# 麻将机自动编号验证

Owner先提到选手ID，随后明确纠正为“麻将机管理的编号”。已撤回选手页面两处临时提示改动，未将选手测试计入本轮麻将机结论。工作分支`codex/machine-auto-number`，基线main `469f38f`。

## 行为

新增麻将机省略machine_no，服务端从001～999选择未被非退役设备使用的最小三位编号。名称/位置/状态/备注照常维护；新建不显示编号输入，编辑只显示真实编号。现有接口显式编号仍兼容，1～3位归一化和现役唯一约束保留；退役号按原规则可复用，新设备有新稳定ID，历史快照不改。编号耗尽明确409，原设备数据不覆盖。

自动/显式创建均在原子事务中进入物理池锁，和状态/赛事分配使用同一顺序。SQLite空池用原有无操作DML写预留；PostgreSQL先使用数据库内事务级advisory锁，再按PK行锁定池，保护空池自动编号。未新增模型、数据库字段或迁移，没有改已有编号、User资料或业务库。

## 本轮实际验证

Windows PowerShell / Python3.13.15、Django5.2.18、SQLite / 项目内Node22.23.4 / Playwright1.65.0、Edge157.0.4341.42；独立QA，dotenv关闭，随机QA密钥及新账号只在忽略目录。

| 项目 | 实际命令/范围 | 结果 |
| --- | --- | --- |
| 后端机器专项 | `manage.py test machines --noinput` | 17项PASS；自动分号、空池并发、三状态跳号、退役复用ID、999耗尽及原权限/CSRF/格式回归 |
| 后端全量 | `manage.py check`、`makemigrations --check --dry-run`、隔离库`migrate --noinput`、`test --noinput` | PASS；无新迁移，197项，46.407秒 |
| 前端机器专项 | `npm test -- --run src/pages/machines.test.tsx` | 15项PASS；新建无编号输入，POST省略编号，名称与角色/错误/focus回归保留 |
| 前端全量/构建 | `npm run typecheck`、`npm test`、`npm run build` | 220项/16文件PASS，构建PASS；保留单JS块超过500kB构建提示 |
| 依赖审计 | `npm audit --audit-level=high --registry=https://registry.npmjs.org --cache .cache/npm` | PASS，0漏洞 |
| 实际HTTP/浏览器 | `.verification/machine-auto-number/browser.cjs`访问隔离localhost HTTPS/Django/SQLite | PASS；只填写名称两次新增得到001/002及不同ID5/6，真实POST不含machine_no，反馈用响应编号，编辑编号只读，390宽无横向溢出 |
| 独立审查 | `/root/score_corrections_reviewer` | 最终源码/日志/浏览器/截图复核PASS，无待修复项 |

日志在`backend/.verification/machine-auto-number/`，可分享证据存[本轮目录](evidence/machine-auto-number)。运行时/缓存/库/凭据/证书/trace保持忽略；QA服务完成后按本实例停止，不终止其他程序。

最终秘密/范围检查PASS：19个候选文件未检出本轮QA密码或私钥；玩家页面、数据模型、历史迁移和依赖锁无修改。QA服务已正常退出，18092/18452及错误目标选手QA的18091/18451无残留监听。

本轮修改了与新需求冲突的前端手填编号断言，保留了后端显式编号格式/重复拒绝/旧接口回归及历史证据；未删除原有效测试。

PostgreSQL空池并发、Linux Docker/正式服务器、本轮GitHub CI和真实业务库仍为**UNVERIFIED**。本轮未进行提交/推送/PR/合并/部署，无新增迁移需要应用。错误目标“选手ID”的临时QA结果不作为本轮证据。
