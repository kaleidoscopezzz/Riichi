# 团队赛隔离QA证据

本目录记录2026-11-10本地候选验证，详情见[验证报告](../../team-tournaments-verification.md)。所有赛事、选手和设备均为独立QA中的真实API测试记录，截图不代表生产数据或正式上线。

- `logs/`：最终后端/前端、迁移、HTTP、浏览器及保留的早期失败日志；仅将本机工具/工作区路径替换为占位符，原始日志仍保留在忽略目录。
- `summaries/`：迁移投影/备份恢复结果、依赖审计、HTTP状态与Cookie属性；没有凭据值。
- `screenshots/browser-candidate/`：团队榜、成员贡献、实时积分/累计变化、位置代表、手动位置分组及手机深浅主题。
- `prior-runs/`：首次失败与随后全套13项中定位断言失败的截图，以及当轮真实已完成的页面。
- `source-manifest.json`：基线SHA、未提交工作树的源码与依赖锁SHA-256；不冒称已经提交或发布。
- `evidence-manifest.json`：本目录证据文件的SHA-256，供审查核对。

QA数据库、备份本体、管理员随机密码、证书私钥、Cookie/CSRF值和Playwright trace不提交。PostgreSQL、Linux容器、GitHub CI及正式服务器仍未验证，旧报告不能替代本轮结果。
