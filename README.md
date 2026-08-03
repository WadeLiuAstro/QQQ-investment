# QQQ 美股投研仪表盘

个人研究用的 QQQ 定投与仓位辅助工具。它以规则引擎输出五档状态及 20%–60% 的通用仓位范围；不保存券商、持仓或现金数据，也不构成投资建议。

仪表盘另含纳斯达克综合指数（^IXIC）日 K 图，供查看市场走势；它不参与 QQQ 的加减仓信号。

## 本地运行

```powershell
.\.venv\Scripts\python.exe -m scripts.refresh_dashboard
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/`。服务运行期间会每 15 分钟自动刷新；也可随时重新运行刷新命令。

## 手机静态版

将 `qqq-dashboard` 分支推送到一个 GitHub **公开仓库**后：

1. 在仓库 **Settings → Pages** 中把 Source 选为 **GitHub Actions**。
2. 在 Actions 页手动运行一次 `Publish dashboard`。
3. GitHub 会提供手机可访问的 Pages 链接；工作流会在工作日每 15 分钟尝试更新静态数据。

GitHub 的定时任务可能延迟，且所有行情数据均为尽力而为的个人研究用途。若来源不可用，仪表盘会保留上次有效值并标记过期。