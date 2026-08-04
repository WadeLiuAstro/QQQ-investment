# P0.4 情景推演 Implementation Plan

**Goal:** 提供只读"如果……会怎样"面板：临时调整 QQQ 价格、RSI(2)、RSI(6)、VIX、回撤或成交量，展示该假设下的预计状态与原因。必须标注"模拟结果，不是当前实时信号"，不能覆盖实际 payload、规则配置或页面正式结论；重置按钮一键恢复实时值。

**Architecture:** 纯前端实现（GitHub Pages 无后端 API）。`app.js` 新增 `simulateScenario` 本地评估函数（复制 decision.py 的状态判定逻辑，仅用于模拟），阈值以常量 `SIM_THRESHOLDS` 声明；新增静态契约测试 **校验 JS 常量与 `config/default_rules.json` 一致**（防规则漂移）；页面新增"情景推演"卡片：6 个数字输入 + 模拟按钮 + 结果区 + 重置按钮。

## Global Constraints

- 不修改 `app/services/decision.py`、`config/default_rules.json`；模拟只影响面板内的结果展示。
- 模拟结果必须带"模拟结果，不是当前实时信号"标识；绝不写回 `dashboard.json` 或 payload。
- 这是唯一允许在前端复制规则判定逻辑的模块（模拟器语义），靠阈值一致性测试 + 文案标识约束漂移风险。
- MA200 不可调（沿用最新快照值）；缺失时价格相关条件不参与判定并在结果中注明。
- 每个 Task 严格 TDD；完成后按 AGENTS.md 同步三份文档。

---

### Task 1: 静态契约与阈值一致性测试

**Files:**
- Test: `tests/test_scenario_static.py`

**测试内容:**
- DOM：`#scenario-panel`、6 个输入（`#sim-price` `#sim-rsi2` `#sim-rsi6` `#sim-drawdown` `#sim-vix` `#sim-volume`）、`#simulate-button`、`#scenario-result`、重置按钮 id。
- JS：`simulateScenario` 函数存在；含"模拟结果"与"不是当前实时信号"标识文案；`SIM_THRESHOLDS` 常量。
- **一致性**：读取 `config/default_rules.json`，断言 JS 中 `SIM_THRESHOLDS` 与 `thresholds.rsi2_oversold / rsi6_oversold / vix_high / drawdown_risk` 数值相同。
- 样式：`.sim` 系列类 + 640px 断点包含 `scenario`。

- [ ] Step 1: 写失败测试。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 最小实现（index.html 面板 + app.js 模拟器 + style.css）。
- [ ] Step 4: `pytest -q` 全量通过。
- [ ] Step 5: 提交 `feat: add what-if scenario simulator panel`。

---

### Task 2: 模拟逻辑与 UI 细节（随 Task 1 一并实现，提交内 TDD）

- `simulateScenario(v, ma200)` 返回 `{state, reasons}`；判定顺序与 `decision.py` 一致（风险≥2→defensive；风险≥1→cautious；RSI 双超卖→opportunity；价≥MA200 且 RSI(6)≥50→constructive；否则 neutral）。
- 结果区渲染：状态中文名 + 原因列表 + "模拟结果，不是当前实时信号"（样式 `sim-badge`）+ 数据不足注明。
- 重置：从最新 payload 的 indicators 恢复输入框默认值；模拟前后不触碰真实信号区。
- 输入框变化不自动模拟（按钮触发），避免刷新风暴。

---

### Task 3: 浏览器核验

- 刷新真实快照 → 打开页面 → 把 RSI(6) 改为 10 → 模拟 → 结果应为"加仓机会"（opportunity）且带模拟标识 → 重置 → 输入恢复真实值。
- 检查控制台零错误；桌面 + 移动端可读。

---

### Task 4: 三份文档同步与最终验收

- [ ] roadmap：P0.4 ✅ + 交付记录 + 提交哈希 + 实施顺序划掉。
- [ ] CONTEXT.md：界面约定补充情景推演卡片与"前端规则复制例外 + 一致性测试"边界。
- [ ] MEMORY.md：记录模拟器为前端规则复制唯一例外，漂移风险靠 `test_scenario_static.py` 一致性断言约束。
- [ ] 全量验收：`pytest -q`、`git diff --check`、`git status --short`。

---

## Plan Self-Review

| 需求项 | 覆盖位置 |
| --- | --- |
| 调整 6 项指标并展示预计状态与原因 | Task 1 面板 + Task 2 simulateScenario |
| "模拟结果，不是当前实时信号"标识 | Task 1 文案断言 + Task 2 sim-badge |
| 不覆盖正式结论 | Global Constraints + 只写 #scenario-result |
| 重置按钮恢复实时值 | Task 2 重置逻辑 + Task 3 核验 |
| 不修改后端规则 | 后端零改动；阈值一致性测试防漂移 |
