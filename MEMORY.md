# 项目记忆

此文件记录跨 agent 交接时仍然有效的决策和已知情况。发生变化时更新对应条目，而不是追加重复历史。

## 已确认的产品决策

- 主要用途是辅助判断 QQQ 的定投节奏与加减仓，不接入券商或执行交易。
- QQQ 使用 RSI(2)、RSI(6)、回撤、200 日均线、VIX、恐贪与成交量等信号；默认状态是中性、目标仓位 40%、定投倍率 1×。
- `^IXIC` 与 QQQ/Nasdaq-100 区分开来，只作 K 线展示。
- 板块 ETF 必须使用中文名称：科技（XLK）、半导体（SMH）、能源（XLE）、金融（XLF）。

## 已知数据源状态

- CNN Fear & Greed 免费端点可能返回 HTTP 418；此时 `cnn_fear_greed` 标为不可用，前端说明其未纳入本次判断。
- BLS 日历端点可能返回 HTTP 403；事件区块应显示暂无可用日历，不影响行情刷新。
- Yahoo Finance 抓取可能短暂失败；`^IXIC` 采用独立快照降级，页面不能将过期数据当成实时数据。

## 发布与缓存

- 仓库：`WadeLiuAstro/QQQ-investment`；Pages 地址为 `https://wadeliuastro.github.io/QQQ-investment/`。
- `main` push 会自动触发 `Publish dashboard`；工作流另有手动和工作日每 15 分钟触发。
- Pages/浏览器会缓存 `index.html`、JavaScript 和 `dashboard.json`。若线上页面看起来旧，先强制刷新或添加临时查询参数进行核验。

## 当前维护原则

- 显示数据源状态和阈值，优先可解释性。
- 页面文案可以改进，但没有用户明确授权时不得调整投资规则。
- 每次功能变更同时验证桌面端和手机端可读性。
