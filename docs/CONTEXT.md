# 项目上下文

> 这是“当前系统事实”的快速索引。若这里与代码冲突，以代码和测试为准；修正后同步更新本文件。

## 产品目标

QQQ 美股投研仪表盘用于辅助长期定投和目标仓位判断。核心输出为五档状态：`defensive`、`cautious`、`neutral`、`constructive`、`opportunity`，对应 20%–60% 的通用仓位范围。它不连接券商、不记录真实持仓，也不构成投资建议。

用户最关心的是“是否应维持、提高或降低本期定投节奏”，因此每个状态都要有可解释的规则原因，而不是黑箱评分。

## 运行形态

- 本地：FastAPI 提供 `/api/dashboard` 与静态页面；后台调度为双模式（S3）：**日频全量刷新**（工作日美东 16:35 cron，产出正式信号）+ **盘中轻量守护**（每 15 分钟，仅常规交易时段内执行，只追加熔断预警）。
- 手机：GitHub Pages 部署 `static/` 目录；Actions 在 push 到 `main`、手动运行和工作日每 15 分钟定时时以 `--mode auto` 刷新数据后部署（盘中自动走守护、盘后走全量）。

### 刷新与数据流

调度双模式（S3）：`app/scheduler.py` 的 `create_refresh_scheduler` 注册两个 job——`daily_refresh`（CronTrigger 工作日 16:35 America/New_York，跑 `refresh_once` 全量）与 `intraday_guard`（interval 15 分钟，跑 `run_intraday_guard`）。守护流程：非交易时段或无日频快照时 no-op；抓 QQQ 与 ^VIX 报价，由 `app/services/intraday_guard.py` 检测熔断（QQQ 单日跌幅 ≤ -3%；VIX 单日涨幅 ≥ +20% 或绝对值 ≥ 35，阈值测试锁定）；命中时按 `circuit_breaker:{日期}:{类型}` key 去重追加提醒并写 `intraday_watch`（checked_at/价格/涨跌幅/triggered），**绝不重算** decision/indicators/backtest/monitoring，也不写状态历史。`scripts/refresh_dashboard.py` 支持 `--mode auto|daily|guard`（auto = 盘中跑守护、盘后跑全量）；手动 `/api/refresh` 仍为全量刷新（开发工具，不属自动节奏）。

日频全量路径：`app/scheduler.py` 调用行情和宏观提供方，生成 market、events、sources、decision、backtest；`app/services/dashboard.py` 负责快照降级；结果写入本地 SQLite 和 `static/data/dashboard.json`。`market.qqq.threshold_matrix` 由 `app/services/explanation.py` 的 `build_threshold_matrix` 生成，包含每行规则的当前值、触发条件、距离、单位、近 5 日方向与可用性。每次刷新会把 decision 快照写入 `state_history` 表，`refresh_once` 组装 payload 顶层 `state_history`（最近 90 天切换事件与当前状态持续时长；decision 为 None 时不生成）。`refresh_once` 还对比相邻快照组装 payload 顶层 `alerts`（边沿事件 + key 去重，低噪声；同一提醒不重复）。FastAPI 从快照/API 提供本地页面，GitHub Actions 重新运行刷新脚本后发布整个 `static/` 目录。

快照语义（S3）：payload 顶层 `snapshot_kind`（默认 "daily"，旧快照兼容）+ `generated_at` 标识"日频正式快照"；盘中页面展示的是最近一次日频快照 + 守护追加的提醒，不会出现盘中估算类模糊正式信号。

`static/assets/app.js` 只做展示与解释，不能自行计算或覆盖仓位状态。页面中显示的状态、仓位、定投倍率都以 payload 中的 `decision` 为准。

**例外（唯一）**：情景推演面板允许在 `simulateScenario` 中复制规则判定逻辑（GitHub Pages 无后端 API），阈值以 `SIM_THRESHOLDS` 常量声明，由 `test_scenario_static.py` 与 `config/default_rules.json` 的一致性断言防漂移；该面板必须标注模拟标识且不写回任何正式数据。

## 数据与决策

- Yahoo Finance / `yfinance`：QQQ、QQQE（等权）、板块 ETF、VIX、^VIX3M、美债收益率、美元指数与 `^IXIC`；QQQ/QQQE 取 2y 周期（结构评分需 252 根窗口），其余取 1y；抓取失败时自动重试 1 次（0.5 秒退避）后才降级；非有限（NaN）的收盘价/成交量行会被过滤，避免污染指标与 K 线。
- 体系参考层（S1）：`market.qqq.trend` 为 MA200 趋势状态机（多头=收盘价≥MA200 收复即算；空头=连续 3 日低于且偏离≥1%；前轮为空头且未收复时保持空头；单月回撤≥8% 触发 `circuit_breaker`），`previous_regime` 从上轮快照读取。`market.qqq.structural_risk` 为四维结构评分（回撤深度 30/速度 20/宽度 25/波动率 25），档位：<40 normal、40–69 watch（加仓减半）、≥70 critical（冻结加仓）；^VIX3M 缺失时仅失去期限倒挂分（10 分），评分仍可用。二者均为参考层，不改变五档正式决策。
- 归因闸门（S2）：`market.qqq.attribution` 含 `evidence`（大跌检测：单日 ≤ -2% 或回撤进入新 5% 档；证据集：当日跌幅/回撤深度与速度/VIX 与 5 日跳升/宽度 RS/3 天内临近事件）、`gate`（open 放行 / half 减半 / frozen 冻结；触发未拍板=half+48h 倒计时，拍板三分类：liquidity_panic→open、structural→frozen、watch→half+48h 复核）、`decision`。拍板持久化在 SQLite `attribution_decisions` 表，`decision_log` 表记录 signal/attribution/execution 三类日志。API：`POST /api/attribution`（拍板，本地服务器）、`GET /api/attribution`、`GET /api/decision-log`；GitHub Pages 静态站无写能力，前端提供"导出 JSON（静态站降级）"下载拍板文件，本地运行才可实时提交。
- 监控佐证层（monitoring）：`DashboardPayload.monitoring`（可选顶层字段，旧快照无此字段时前端隐藏）含 `summary`（四张固定摘要：sentiment/core_trend/breadth/volatility）与 `groups`（四个固定分组：sentiment_volatility/core_breadth/sector_rotation/macro_defensive）。统一口径：latest + change_1d + direction_5d + momentum_20d + as_of + available/stale。由 `app/services/monitoring.py` 纯函数组装，在正式决策计算**之后**附加，绝不传入 `evaluate_decision()`。CNN 七因子与历史为可选增量字段，缺失只降级对应子区不影响总分；整体构建失败时 `mark_monitoring_stale` 复用上一快照并标 stale。`sentiment_volatility.details` 额外含 `gauge_value`/`gauge_label`（仪表盘当前值与五档标签）与 `comparisons`（结构化 `MonitoringComparison`：上一交易日/一周前/一月前/一年前，日期按观测日自动回算）；旧快照 comparisons 为 dict 时由 `MonitoringDetails` 的 `field_validator` 转为空 list 以兼容。情绪五档阈值由 `_cnn_status` 定义（0-25 恐惧/25-45 谨慎/45-55 中性/55-75 乐观/75-100 贪婪），前端 FG_BANDS 色带区间须与其一致。`details.history` 由 `_recent_history` 只保留最近 366 天内的点并按时间升序，供前端"近一年市场情绪走势"图使用；历史缺失时前端显示"暂无历史走势数据"，不伪造数据。
- `is_intraday_estimate` 由 `app/services/session.py` 按美东常规交易时段（周一至周五 9:30–16:00，节假日不识别）计算：盘中为"盘中估算"，收盘后为"收盘正式"。
- 每个市场卡带 `stale_lag`（最新 bar 距最近已收盘交易日的滞后交易日数，由 `expected_bar_date` 判定基准）；滞后 ≥1 个交易日时前端标注"数据滞后 N 个交易日"。已知根因：Yahoo 盘后对当日 bar 返回 Close=NaN 被过滤后数据停留上一交易日，标注随数据恢复自动消失。
- 盘中成交量比率按已交易时段占比外推（分母下限 0.05）并标记 `volume_is_estimated`，阈值矩阵与信号拆解注明"盘中估算"；收盘后使用原始成交量，行为不变。
- CNN Fear & Greed：仅作为可选辅助数据；不可用时不参与判断。
- 消息面（news）：payload 顶层 `news`（可选，旧快照无此字段时前端隐藏），含 `upcoming`（未来 45 天内最近最多 10 个宏观事件，升序，含 days_until）与 `headlines`（最近 3 天、最多 12 条、时间降序）。事件抓取窗口 `EVENT_WINDOW_DAYS=45`（服务日历，覆盖如 41 天后的 FOMC）；监控区"临近高影响事件"另行预过滤 `MONITORING_EVENT_WINDOW_DAYS=7` 保持"临近"语义；alerts/归因各自按 3 天窗口独立过滤。数据源混合：现有宏观日历（FOMC/CPI/非农）打底 + CNBC RSS 双源（宏观 Economy + US Top News，中文来源名"CNBC 宏观"/"CNBC 头条"，浏览器请求头抓取，stdlib xml.etree 解析）；日历失败→upcoming 空，RSS 失败→`news_source_available=false` 头条区降级文案，两者都失败→`available=false`。随日频全量刷新一天一次，盘中守护不抓新闻；纯展示，永不耦合决策。
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
- 顶部信号带即"本期行动卡"：状态、仓位区间、定投倍率 + "额外加仓""数据完整度"chips + "关键观察条件"列表；观察条件按状态固定映射（见 `app/services/action_card.py`），数据来自 payload 顶层 `action_card`。
- 阈值距离矩阵（`threshold_matrix`）展示在信号拆解区域顶部：5 行固定顺序（RSI(2) 超卖、RSI(6) 超卖、回撤风险、VIX、异常放量），列包含当前值、触发条件、距离、近 5 日方向。已触发的风险行用红色、机会行用绿色；数据不可用时行标为"未参与本次判断"。
- 状态历史卡片展示最近 90 天切换事件（时间、状态、仓位区间、定投倍率、原因）与当前状态持续时长（刷新次数）；无 `state_history` 字段（旧快照）时隐藏。
- 情景推演卡片：6 个输入（价格/RSI(2)/RSI(6)/回撤/VIX/成交量比）+ 模拟/重置；结果区强制带"模拟结果，不是当前实时信号"标识，只写入 `#scenario-result`，绝不覆盖正式结论。
- 顶部提醒条（`alerts`）：六类提醒（状态切换/阈值进入缓冲/进入防御/数据源持续失败/FOMC·CPI·非农临近/熔断预警 circuit_breaker），带"仅页面内提醒，不推送"注记；空列表或旧快照无该字段时整个横幅隐藏。
- 数据状态区（`#data-status`）：开头展示"日频正式快照 · 生成于 {generated_at}"标注（`snapshot_kind==='daily'` 时）；`intraday_watch` 存在时追加"盘中守护 {checked_at} · 正常/已触发熔断预警"（触发时红色）。
- 市场宽度佐证卡片：QQQE 相对 QQQ 的 5/20 日强弱与四态标签（集中度偏高/等权同步走强/宽度与指数同步/回调期宽度观察）；纯佐证展示，绝不参与决策；数据不足时标"未参与本次判断"。
- 体系趋势层卡片（`trend-card`）：多头/空头徽标 + 偏离 MA200 百分比 + 连续低于天数 + 熔断触发 chip；数据不足标"趋势数据不可用（需 200 日历史）"。
- 结构性风险卡片（`structural-card`）：档位徽标（正常/警示/疑似结构性）+ 总分 + 四维分解（回撤深度/回撤速度/宽度恶化/波动率体制）；均带"参考层"标识。
- 大跌归因卡片（`attribution-card`）：闸门徽标（放行/减半/冻结）+ 证据集（当日跌幅/回撤/VIX+跳升/宽度 RS/临近事件）+ 拍板截止或复核截止倒计时 + 三选一拍板表单（分类下拉 + 理由必填）；已拍板后显示结论并隐藏表单；提交失败（静态站）提示导出 JSON 走手动流程。
- 决策日志卡片（`decision-log-card`）：时间轴展示 signal/attribution/execution 三类日志；本地服务拉取 `/api/decision-log`，静态站或空库时显示对应空态文案。
- 监控指标增强区（`#monitoring-section`，B 位：QQQ/宏观 hero 之后、事件卡之前）：顶部四张摘要卡（CNN 市场情绪/QQQ 核心趋势/市场宽度/波动率体制）+ 四个可点击分组手风琴（情绪与波动/核心趋势与宽度/板块轮动/宏观与防御）。互斥展开（同时最多一组），分组按钮用原生 `<button>` + `aria-expanded`/`aria-controls` 支持键盘；展开状态写 `sessionStorage`（key `monitoring-open-group`），不入库不上传。`payload.monitoring` 缺失时整个 section 隐藏。只做事实陈述（上行/下行/平稳/期限倒挂等），不含买入/卖出/加仓/减仓字样；VIX 上升用红（风险升温），CNN 按恐惧—贪婪区间着色。桌面摘要四列、手机 2×2。
- 消息面卡片（`#news-section`，monitoring-section 之后）：标题"消息面 · 预期与头条"——预期事件区为**当月网格月历**（周一起始 7 列，表头 一二三四五六日，事件日 `<button class="nc-day has-event">` 圆点标注，days_until≤7 琥珀/其余绿色，点按在 `#news-cal-readout` 显示"YYYY-MM-DD · 事件名"，跨月事件在网格末尾标"+N 下月事件"，无事件时保留"暂无排期事件"）+ "近三日关键头条"列表（时间｜中文来源徽标｜英文标题原文｜"原文↗"链接 target=_blank rel=noopener）+ 脚注"随日频快照更新 · 覆盖最近 3 天 · 最多 12 条 · 仅陈述事实，不构成任何判断依据"；降级文案："新闻源暂不可用，仅展示排期事件"/"近三日暂无收录头条"/"消息面暂不可用"；标题/来源/URL 拼接前经 HTML 转义；`p.news` 缺失时整个 section 隐藏；手机压缩网格。
- 顶部头条摘要栏（`#news-ticker-bar`，信号带之后，role=note + tabindex=0 键盘可达）：常驻标注"消息面 · 日频更新 {时间}"（不暗示实时）+ 最新最多 3 条头条叠位淡入淡出轮换（8 秒/条，opacity 过渡 0.6s，mouseenter/focusin 暂停），`prefers-reduced-motion` 时静态显示第一条；点击/Enter 平滑滚动到 `#news-section`；头条为空时整栏隐藏；纯 CSS/JS 实现无第三方动效库。
- 情绪与波动分组内的 CNN 情绪子区顺序：SVG 仪表盘 gauge（中心数值在表盘下方正常流布局，不与指针重叠）→ 综合判断横幅 → 四张历史对比卡 → **近一年市场情绪走势图**（`#fg-history-chart`，Lightweight Charts 折线，Y 轴固定 0–100，四条虚线分档线 25/45/55/75 带"恐惧/谨慎/中性/乐观 ≤N"标签，颜色与 FG_BANDS 一致；悬停/点按在 `#fg-history-readout` 显示日期·分数·五档标签）→ CNN 七项分因子 → VIX/VIX3M 行。历史为空时显示"暂无历史走势数据（CNN 情绪历史不可用）"；分组重新展开时会先销毁旧图表实例再重建。
- ^IXIC K 线为日K（每根=1 交易日，`interval=1d`），界面显式标注"日K · 每根=1 交易日"；1月/3月/6月/1年为时间范围切换而非粒度切换。

## 关键文件地图

| 目的 | 主要文件 |
| --- | --- |
| API、应用生命周期、静态文件 | `app/main.py` |
| 行情聚合、双模式调度（日频全量 + 盘中守护）、快照导出 | `app/scheduler.py` |
| 盘中熔断检测与预警（QQQ -3% / VIX +20% 或 ≥35） | `app/services/intraday_guard.py` |
| CNBC RSS 头条抓取与解析（降级优先） | `app/providers/news_rss.py` |
| 消息面卡片组装（3 天窗口/12 条上限/降级矩阵） | `app/services/newsboard.py` |
| 双模式刷新入口（auto/daily/guard） | `scripts/refresh_dashboard.py` |
| QQQ 状态规则 | `app/services/decision.py` |
| 本期行动卡（加仓判定、观察条件、完整度） | `app/services/action_card.py` |
| 状态历史切换与持续时长 | `app/services/state_history.py` |
| 低噪声提醒（边沿事件 + 去重） | `app/services/alerts.py` |
| 市场宽度佐证（QQQE vs QQQ） | `app/services/breadth.py` |
| MA200 趋势状态机 + 熔断 | `app/services/trend.py` |
| 结构性风险四维评分 | `app/services/structural.py` |
| 大跌检测 + 归因闸门 | `app/services/attribution.py` |
| 监控指标增强区（佐证层） | `app/services/monitoring.py` |
| 阈值距离与方向矩阵 | `app/services/explanation.py` |
| 美东交易时段判断 | `app/services/session.py` |
| RSI、均线、回撤、成交量等指标 | `app/services/indicators.py` |
| 快照和单模块降级 | `app/services/dashboard.py`、`app/db.py` |
| 数据源适配 | `app/providers/` |
| 页面与 K 线交互 | `static/index.html`、`static/assets/app.js`、`static/assets/style.css` |
| Pages 发布 | `.github/workflows/publish-dashboard.yml` |

## 验证基线

当前测试命令为 `./.venv/Scripts/python.exe -m pytest -q`。不要把 `static/data/dashboard.json` 或 SQLite 快照提交到 Git。前端暂时没有独立 JavaScript 测试运行器，因此使用 pytest 静态契约测试并配合浏览器实际渲染核验。