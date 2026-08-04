# P0.2 本期行动卡 Implementation Plan

**Goal:** 将顶部信号带升级为"本期行动卡"：一眼看到当前状态、建议仓位区间、定投倍率、额外加仓是否满足、数据完整度与下一组关键观察条件。纯解释层，不改变任何决策规则。

**Architecture:** 新增 `app/services/action_card.py` 纯函数服务，从 `indicators`、`rules`、`decision`、`sources` 生成 `ActionCard`；`scheduler` 接线写入 payload 顶层 `action_card`；前端将 `#signal-band` 扩展为行动卡（chips + 观察条件列表）。

## Global Constraints

- 禁止修改 `app/services/decision.py`、`config/default_rules.json` 的阈值与决策逻辑；本模块只读这些规则做展示。
- 状态→观察条件的映射为固定产品语义（写入测试），改映射需用户授权。
- 基础定投金额（localStorage 设置与金额示例）为"后续可允许"，**本迭代不实现**。
- 每个 Task 严格 TDD；任务完成后按 AGENTS.md 同步三份文档。

---

### Task 1: ActionCard 服务与模型

**Files:**
- Modify: `app/models.py`（`WatchCondition`、`ActionCard`）
- Add: `app/services/action_card.py`
- Test: `tests/test_action_card.py`

**模型:**

```python
class WatchCondition(BaseModel):
    label: str          # 如 "RSI(2) 与 RSI(6) 进入超卖"
    condition: str      # 如 "RSI(2) ≤ 15 且 RSI(6) ≤ 30"
    met: bool           # 当前是否已满足
    note: str | None    # 数据不足时说明

class ActionCard(BaseModel):
    extra_top_up_ready: bool
    extra_top_up_reason: str
    watch_conditions: list[WatchCondition]
    data_completeness: dict[str, object]  # {"available": n, "total": m, "missing": [中文名]}
```

**服务接口:**

```python
def build_action_card(indicators, decision, rules, sources) -> ActionCard
```

**规则:**
- `extra_top_up_ready`：rsi2、rsi6 均可用且 ≤ 各自阈值（与 `decision._is_oversold` 同源）；任一缺失 → ready=False，reason 注明"数据不足"。
- 观察条件按 `decision.state` 映射（固定 4 组，见 Step 1 测试），每条含 `met`（当前是否达成）与 `note`（对应指标为 None 时 = "暂无数据"）。
- `data_completeness`：total = len(sources)；available = 可用数；missing = 不可用源的中文名列表（映射表内置：yahoo_qqq→"QQQ 行情"、cnn_fear_greed→"恐慌贪婪指数"、macro_calendar→"宏观日历" 等）。

- [ ] Step 1: 写失败测试 `tests/test_action_card.py`（9 个用例）：加仓满足/不满足/数据缺失；4 个状态的观察条件 label 集合与 condition 字符串；met 与 note；数据完整度统计与 missing 中文名。
- [ ] Step 2: 运行确认失败（ImportError）。
- [ ] Step 3: 最小实现。
- [ ] Step 4: `pytest -q` 全量通过。
- [ ] Step 5: 提交 `feat: add action card service with watch conditions`。

---

### Task 2: payload 接线

**Files:**
- Modify: `app/models.py`（`DashboardPayload.action_card`）
- Modify: `app/services/dashboard.py`（透传 `action_card` 参数）
- Modify: `app/scheduler.py`（决策后构建并传入）
- Test: `tests/test_action_card_payload.py`

- [ ] Step 1: 写失败测试：复用 `test_threshold_matrix_payload.py` 的 mock 模式（文件内复制 install_mocks），断言 payload.action_card 含 5 键、extra_top_up_ready 与独立重算一致、decision 字段不变（防回归）、qqq 数据缺失时 action_card 为 None。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 最小实现。
- [ ] Step 4: 全量测试通过。
- [ ] Step 5: 提交 `feat: expose action card in dashboard payload`。

---

### Task 3: 前端行动卡渲染与响应式

**Files:**
- Modify: `static/index.html`（signal-band 增加 `#extra-topup`、`#completeness` chips；新增 `#watch-conditions` 容器）
- Modify: `static/assets/app.js`（`renderActionCard`；旧快照无 action_card 时隐藏 chips 与观察列表）
- Modify: `static/assets/style.css`（chip / watch 列表样式 + 640px 断点）
- Test: `tests/test_action_card_static.py`

**前端规则:**
- 额外加仓：ready → "额外加仓 可执行"（positive）；否则 "额外加仓 未满足"（muted），title 显示 reason。
- 数据完整度：`数据完整度 X/Y`；missing 非空时 title 列出缺失源。
- 观察条件：`● 已满足`（positive）/ `○ 观察中`（muted）+ label（condition）；note 存在时显示 "暂无数据" 标记。
- 无 `action_card`（旧快照）时全部隐藏，不影响其它区块。

- [ ] Step 1: 写失败测试（静态契约：DOM id、关键文案、样式类、640px 断点）。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 最小实现。
- [ ] Step 4: 全量测试通过；刷新真实快照；浏览器核验桌面与 375px 手机端。
- [ ] Step 5: 提交 `feat: render action card on dashboard`。

---

### Task 4: 三份文档同步与最终验收

- [ ] roadmap：P0.2 ✅ + 交付记录 + 提交哈希 + 推荐顺序划掉。
- [ ] CONTEXT.md：payload 新增 `action_card` 字段、文件地图新增 action_card.py、界面约定补充行动卡。
- [ ] MEMORY.md：记录"行动卡观察条件为固定状态映射，改需授权"。
- [ ] 全量验收：`pytest -q`、`git diff --check`、`git status --short`。

---

## Plan Self-Review

| 需求项 | 覆盖位置 |
| --- | --- |
| 状态/仓位/倍率/额外加仓/完整度/观察条件 | Task 1 模型 + Task 3 渲染 |
| 桌面与手机一眼可读 | Task 3 chips + 640px 断点 + 人工核验 |
| 不改变决策规则 | Global Constraints + Task 2 防回归断言 |
| 旧快照兼容 | Task 3 无 action_card 隐藏 |
| 本地金额设置暂缓 | 明示排除在迭代外 |
