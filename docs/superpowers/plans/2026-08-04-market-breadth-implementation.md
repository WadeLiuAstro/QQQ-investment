# P2.1 市场宽度与集中度 Implementation Plan

**Goal:** 新增"市场宽度佐证"：展示 QQQE（纳斯达克 100 等权）相对 QQQ 的 5/20 日强弱与集中度标签（如"上涨集中度偏高"）。**初期只显示为佐证，不改变五档状态**（P2 全局原则）。

**Architecture:** `SYMBOLS` 增加 `qqqe: QQQE`；新增纯函数服务 `app/services/breadth.py`：`build_breadth(qqq_bars, qqqe_bars)` 计算相对强弱与标签；`scheduler` 写入 `market["qqq"]["breadth"]`；前端新增"市场宽度佐证"小卡。

## Global Constraints

- 不修改 `app/services/decision.py` 与规则配置；breadth 绝不进入决策。
- 标签为固定产品语义（写入测试）：QQQ 20 日涨幅 > 0 且 RS(20d) ≤ -1 → "上涨集中度偏高"；≥ 1 → "等权同步走强"；介于之间 → "宽度与指数同步"；QQQ 跌 → "回调期宽度观察"。数据不足 → available=False。
- RS = QQQE 涨幅 − QQQ 涨幅（百分点）。
- 每个 Task 严格 TDD；完成后按 AGENTS.md 同步三份文档。

---

### Task 1: breadth 服务

**Files:**
- Modify: `app/models.py`（`Breadth`）
- Add: `app/services/breadth.py`
- Test: `tests/test_breadth.py`

```python
class Breadth(BaseModel):
    qqqe_price: float | None
    relative_strength_5d: float | None
    relative_strength_20d: float | None
    qqq_return_20d: float | None
    label: str | None
    available: bool
    note: str | None
```

- [ ] Step 1: 写失败测试（约 8 个用例）：四态标签、RS 数值、5/20 日计算、数据不足（bars 太短、QQQE 失败）。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 最小实现。
- [ ] Step 4: `pytest -q` 全量通过（注意 action_card 的 total 12→13 断言需同步更新）。
- [ ] Step 5: 提交 `feat: add market breadth service`。

---

### Task 2: scheduler 接线

**Files:**
- Modify: `app/scheduler.py`（SYMBOLS + qqqe，decision 分支后写 `market["qqq"]["breadth"]`）
- Test: `tests/test_breadth_payload.py`

- [ ] Step 1: 写失败测试：payload 含 breadth 且与独立重算一致；QQQE 失败 → breadth available=False 且 decision 不变（防回归）。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 最小实现。
- [ ] Step 4: 全量测试通过。
- [ ] Step 5: 提交 `feat: expose market breadth in payload`。

---

### Task 3: 前端佐证卡片

**Files:**
- Modify: `static/index.html`（`#breadth-card`）
- Modify: `static/assets/app.js`（`renderBreadth`；无 breadth 时隐藏）
- Modify: `static/assets/style.css`
- Test: `tests/test_breadth_static.py`

**前端规则:** QQQE 价格 + RS(20d)（带正负号）+ 标签；标签着色：集中度偏高 → amber，同步走强 → mint。

- [ ] Step 1: 写失败测试（静态契约）。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 最小实现。
- [ ] Step 4: 全量测试通过；刷新真实快照；浏览器核验桌面与手机端。
- [ ] Step 5: 提交 `feat: render market breadth card`。

---

### Task 4: 三份文档同步与最终验收

- [ ] roadmap：P2.1 ✅ + 交付记录 + 提交哈希 + 实施顺序划掉。
- [ ] CONTEXT.md：数据流（QQQE、breadth 字段）、文件地图新增 breadth.py、界面约定。
- [ ] MEMORY.md：记录"breadth 为佐证层第一个指标，标签语义固定，改需授权"。
- [ ] 全量验收：`pytest -q`、`git diff --check`、`git status --short`。

---

## Plan Self-Review

| 需求项 | 覆盖位置 |
| --- | --- |
| QQQE 相对 QQQ 强弱（5/20 日） | Task 1 RS 计算 |
| 集中度标签语义 | Task 1 四态 + 测试 |
| 只作佐证不改决策 | Global Constraints + Task 2 防回归 |
| 数据不足降级 | Task 1 available=False |
