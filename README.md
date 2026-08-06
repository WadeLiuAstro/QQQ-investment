# QQQ 美股投研仪表盘

个人研究用的 QQQ 定投与仓位辅助工具。设计依据为 [`docs/investment-system.md`](docs/investment-system.md)（投资交易体系 v1.0）。不连接券商、不保存持仓/现金/密钥，也不构成投资建议。

在线版（GitHub Pages，手机可访问）：<https://wadeliuastro.github.io/QQQ-investment/>

## 正式决策输出

规则引擎（`app/services/decision.py`）输出五档状态与通用仓位范围，是唯一正式信号，一切解释透明可复核：

| 状态 | 触发逻辑 |
| --- | --- |
| 防御 defensive | 两项及以上风险条件（跌破 200 日均线 / 回撤 ≤ -12% / VIX ≥ 30） |
| 谨慎 cautious | 一项风险条件 |
| 加仓机会 opportunity | RSI(2) ≤ 15 且 RSI(6) ≤ 30 双超卖 |
| 建设性加仓 constructive | 价格 ≥ 200 日均线且 RSI(6) ≥ 50 |
| 中性 neutral | 其余情形（默认目标仓位 40%、定投倍率 1×） |

## 主要功能

**决策闭环**
- 阈值距离矩阵：每条规则的当前值、触发条件、剩余距离、近 5 日方向
- 本期行动卡：状态 / 仓位区间 / 定投倍率 / 额外加仓判定 / 关键观察条件 / 数据完整度
- 状态历史时间轴：最近 90 天切换记录与持续时长
- 情景推演：只读模拟器（标注"模拟结果，不是当前实时信号"）
- 低噪声提醒：状态切换 / 阈值临近 / 多重风险 / 数据源持续失败 / FOMC·CPI·非农临近 / 熔断预警，边沿触发 + 去重，仅页面内展示

**体系参考层（不改变正式决策）**
- MA200 趋势状态机（多头/空头/待确认 + 单月 -8% 熔断）
- 结构性风险四维评分（回撤深度/速度/宽度/波动率体制，0–100，<40 正常 / 40–69 警示 / ≥70 疑似结构性）
- 大跌归因拍板：机器举证（VIX 跳升、宽度、事件、回撤速度）→ 人拍板三分类（流动性恐慌/结构性/待观察）→ 闸门放行/减半/冻结，超时未拍板自动减半；拍板与信号写入决策日志
- 仓位映射参考层（S4，规划中）

**监控佐证层（纯展示）**
- 四张摘要卡 + 四个分组手风琴（情绪与波动 / 核心趋势与宽度 / 板块轮动 / 宏观与防御）
- CNN 恐惧贪婪指数：五档仪表盘、历史对比卡、近一年走势图（分档线与后端阈值同源）
- 市场宽度：QQQE vs QQQ 相对强弱四态标签
- 消息面：顶部头条摘要栏（淡入淡出轮换，日频标注）+ 消息面卡片（当月网格月历 + 近三日关键头条，CNBC RSS 双源）
- 纳斯达克综合指数（^IXIC）日 K 图（仅作市场走势展示，不参与信号）

## 刷新架构（日频决策节奏）

- **日频全量刷新**：工作日美东 16:35 产出正式快照（`snapshot_kind: "daily"`），正式信号一律基于日频收盘价
- **盘中轻量守护**：每 15 分钟仅检测熔断级事件（QQQ 单日 ≤ -3%；VIX 单日 ≥ +20% 或 ≥ 35），只追加提醒，绝不重算正式决策
- 数据源失败一律优雅降级：保留上次有效快照并标记过期/滞后，绝不伪造实时数据

## 数据源

Yahoo Finance（QQQ/QQQE/板块 ETF/VIX/VIX3M/美债/美元指数/^IXIC）、CNN Fear & Greed、CNBC RSS（宏观 + 头条）、美联储 FOMC 日历、BLS 发布排期。来源状态、时间与可用性在页面底部实时展示。

## 本地运行

```powershell
pip install -r requirements.txt
python -m scripts.refresh_dashboard          # 可选 --mode auto|daily|guard
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/`。服务运行期间按双模式调度自动刷新；`POST /api/refresh` 可手动触发全量刷新（开发用）。测试：`python -m pytest tests -q`。

## GitHub Pages 部署

推送到公开仓库后：Settings → Pages 选 **GitHub Actions** 作为 Source；Actions 的 `Publish dashboard` 工作流在 push 到 `main`、手动运行和工作日每 15 分钟定时时以 `--mode auto` 刷新数据并部署 `static/`。

GitHub 定时任务可能延迟，行情数据均为尽力而为的个人研究用途。

## 协作开发

多代理协作规范见 [`AGENTS.md`](AGENTS.md)（角色分工、独立 worktree + 独立分支的任务派发与验收流程、TDD 约定）；系统现状见 [`CONTEXT.md`](CONTEXT.md)，关键决策记录见 [`MEMORY.md`](MEMORY.md)。
