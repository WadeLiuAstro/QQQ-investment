# 项目上下文

> 这是“当前系统事实”的快速索引。若这里与代码冲突，以代码和测试为准；修正后同步更新本文件。

## 产品目标

QQQ 美股投研仪表盘用于辅助长期定投和目标仓位判断。核心输出为五档状态：`defensive`、`cautious`、`neutral`、`constructive`、`opportunity`，对应 20%–60% 的通用仓位范围。它不连接券商、不记录真实持仓，也不构成投资建议。

用户最关心的是“是否应维持、提高或降低本期定投节奏”，因此每个状态都要有可解释的规则原因，而不是黑箱评分。

## 运行形态

- 本地：FastAPI 提供 `/api/dashboard` 与静态页面；后台每 15 分钟刷新。
- 手机：GitHub Pages 部署 `static/` 目录；Actions 在 push 到 `main`、手动运行和工作日定时任务时刷新数据后部署。

### 刷新与数据流

`app/scheduler.py` 调用行情和宏观提供方，生成 market、events、sources、decision、backtest；`app/services/dashboard.py` 负责快照降级；结果写入本地 SQLite 和 `static/data/dashboard.json`。`market.qqq.threshold_matrix` 由 `app/services/explanation.py` 的 `build_threshold_matrix` 生成，包含每行规则的当前值、触发条件、距离、单位、近 5 日方向与可用性。FastAPI 从快照/API 提供本地页面，GitHub Actions 重新运行刷新脚本后发布整个 `static/` 目录。

`static/assets/app.js` 只做展示与解释，不能自行计算或覆盖仓位状态。页面中显示的状态、仓位、定投倍率都以 payload 中的 `decision` 为准。

## 数据与决策

- Yahoo Finance / `yfinance`：QQQ、板块 ETF、VIX、美债收益率、美元指数与 `^IXIC`；抓取失败时自动重试 1 次（0.5 秒退避）后才降级；非有限（NaN）的收盘价/成交量行会被过滤，避免污染指标与 K 线。
- `is_intraday_estimate` 由 `app/services/session.py` 按美东常规交易时段（周一至周五 9:30–16:00，节假日不识别）计算：盘中为"盘中估算"，收盘后为"收盘正式"。
- 盘中成交量比率按已交易时段占比外推（分母下限 0.05）并标记 `volume_is_estimated`，阈值矩阵与信号拆解注明"盘中估算"；收盘后使用原始成交量，行为不变。
- CNN Fear & Greed：仅作为可选辅助数据；不可用时不参与判断。
- BLS 宏观日历：失败时显示不可用，不中断其它模块。
- `^IXIC`：展示近一年日 OHLC，前端默认 3 个月 K 线；不参与决策。
- QQQ 决策由 `app/services/decision.py` 与规则配置共同输出，前端只负责解释与展示。

### 当前规则接口

规则的实现入口是 `evaluate_decision(indicators, rules)`；前端不应复制或偷偷改变它。当前关键阈值为：RSI(2) 超卖 15、RSI(6) 超卖 30、VIX 风险线 30、回撤风险线 -12%、异常成交量 2 倍。

- 风险状态：价格跌破 200 日均线、回撤达到风险线、VIX 达到风险线中的一个或多个。
- 加仓机会：RSI(2) 与 RSI(6) 同时处于超卖区间。
- 建设性加仓：价格不低于 200 日均线且 RSI(6) 不低于 50。
- 中性：不满足以上更高优先级条件；默认目标仓位 40%、定投倍率 1×。

这些规则是产品契约。改动阈值、优先级或状态含义前，必须获得用户的明确授权，并同步更新测试、`CONTEXT.md` 和 `MEMORY.md`。

## 重要界面约定

- 顶部信号带之后显示 `^IXIC` K 线卡片。
- 板块佐证为中文名称、ETF 代码和价格的单行横向卡片；桌面两列、手机单列。
- VIX 需标为“VIX（恐慌指数）”。
- 信号拆解必须显示当前值与规则阈值，而非只显示"未触发"。
- 阈值距离矩阵（`threshold_matrix`）展示在信号拆解区域顶部：5 行固定顺序（RSI(2) 超卖、RSI(6) 超卖、回撤风险、VIX、异常放量），列包含当前值、触发条件、距离、近 5 日方向。已触发的风险行用红色、机会行用绿色；数据不可用时行标为"未参与本次判断"。

## 关键文件地图

| 目的 | 主要文件 |
| --- | --- |
| API、应用生命周期、静态文件 | `app/main.py` |
| 行情聚合、15 分钟调度、快照导出 | `app/scheduler.py` |
| QQQ 状态规则 | `app/services/decision.py` |
| 阈值距离与方向矩阵 | `app/services/explanation.py` |
| 美东交易时段判断 | `app/services/session.py` |
| RSI、均线、回撤、成交量等指标 | `app/services/indicators.py` |
| 快照和单模块降级 | `app/services/dashboard.py`、`app/db.py` |
| 数据源适配 | `app/providers/` |
| 页面与 K 线交互 | `static/index.html`、`static/assets/app.js`、`static/assets/style.css` |
| Pages 发布 | `.github/workflows/publish-dashboard.yml` |

## 验证基线

当前测试命令为 `./.venv/Scripts/python.exe -m pytest -q`。不要把 `static/data/dashboard.json` 或 SQLite 快照提交到 Git。前端暂时没有独立 JavaScript 测试运行器，因此使用 pytest 静态契约测试并配合浏览器实际渲染核验。