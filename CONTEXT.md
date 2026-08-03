# 项目上下文

## 产品目标

QQQ 美股投研仪表盘用于辅助长期定投和目标仓位判断。核心输出为五档状态：`defensive`、`cautious`、`neutral`、`constructive`、`opportunity`，对应 20%–60% 的通用仓位范围。

## 运行形态

- 本地：FastAPI 提供 `/api/dashboard` 与静态页面；后台每 15 分钟刷新。
- 手机：GitHub Pages 部署 `static/` 目录；Actions 在 push 到 `main`、手动运行和工作日定时任务时刷新数据后部署。

## 数据与决策

- Yahoo Finance / `yfinance`：QQQ、板块 ETF、VIX、美债收益率、美元指数与 `^IXIC`。
- CNN Fear & Greed：仅作为可选辅助数据；不可用时不参与判断。
- BLS 宏观日历：失败时显示不可用，不中断其它模块。
- `^IXIC`：展示近一年日 OHLC，前端默认 3 个月 K 线；不参与决策。
- QQQ 决策由 `app/services/decision.py` 与规则配置共同输出，前端只负责解释与展示。

## 重要界面约定

- 顶部信号带之后显示 `^IXIC` K 线卡片。
- 板块佐证为中文名称、ETF 代码和价格的单行横向卡片；桌面两列、手机单列。
- VIX 需标为“VIX（恐慌指数）”。
- 信号拆解必须显示当前值与规则阈值，而非只显示“未触发”。

## 验证基线

当前测试命令为 `./.venv/Scripts/python.exe -m pytest -q`。不要把 `static/data/dashboard.json` 或 SQLite 快照提交到 Git。
