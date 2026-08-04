# P0.3 状态历史时间轴 Implementation Plan

**Goal:** 提供最近 90 天的状态变化记录：每次切换的日期与原因、建议仓位和定投倍率、当前状态已持续时长。首次实现只展示状态切换记录，不包含收益统计（roadmap 已注明后续再补）。

**Architecture:** 新增 SQLite 表 `state_history`（每次刷新记录一条，含 decision 快照字段）；`SnapshotRepository` 增加 `record_state` / `load_state_history`；新增纯函数服务 `app/services/state_history.py` 从记录序列计算切换事件与当前持续时长；`refresh_once` 组装 `payload.state_history`；前端新增时间轴卡片。

## Global Constraints

- 禁止修改 `app/services/decision.py` 与规则配置。
- 每次刷新都记录一条（含状态未变时），90 天窗口由查询侧过滤；记录不参与任何决策。
- `state_history` 为纯展示字段：`decision` 为 None 时不记录，前端隐藏时间轴。
- 每个 Task 严格 TDD；完成后按 AGENTS.md 同步三份文档。

---

### Task 1: 数据表与入库

**Files:**
- Modify: `app/models.py`（`StateRecord`、`StateSwitch`、`StateHistory`）
- Modify: `app/db.py`（建表、`record_state`、`load_state_history(since_iso)`）
- Test: `tests/test_db.py` 追加

**模型:**

```python
class StateRecord(BaseModel):
    generated_at: datetime
    state: str
    allocation_min: int
    allocation_max: int
    dca_multiplier: float
    reasons: list[str]

class StateSwitch(BaseModel):
    observed_at: datetime
    state: str
    allocation_min: int
    allocation_max: int
    dca_multiplier: float
    reasons: list[str]

class StateHistory(BaseModel):
    switches: list[StateSwitch]
    current_duration_ticks: int
```

**Repository:**

```python
def record_state(self, payload: DashboardPayload) -> None: ...   # decision 为 None 时不写
def load_state_history(self, since_iso: str | None = None) -> list[StateRecord]: ...  # 时间正序
```

- [ ] Step 1: 写失败测试：record→load 往返；decision=None 不记录；`since_iso` 过滤 90 天窗口。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 最小实现。
- [ ] Step 4: `pytest -q` 全量通过。
- [ ] Step 5: 提交 `feat: persist state history rows on refresh`。

---

### Task 2: 时间轴服务与 payload 接线

**Files:**
- Add: `app/services/state_history.py`
- Modify: `app/models.py`（`DashboardPayload.state_history`）
- Modify: `app/scheduler.py`（`refresh_once` 组装 state_history；`collect_dashboard_payload` 返回时写入）
- Test: `tests/test_state_history.py`、`tests/test_state_history_payload.py`

**服务:**

```python
def build_state_history(records: Sequence[StateRecord]) -> StateHistory:
    # switches：首条记录 + 状态与上一条不同的记录（按时间正序）
    # current_duration_ticks：末尾连续相同状态的记录数（含最后一条）
```

**refresh_once 流程调整：** save_payload → record_state → load_state_history → `payload.model_copy(update={"state_history": ...})` → 再次 save_payload → source status → 写 JSON。顺序保证最新 payload 与历史同库。

- [ ] Step 1: 写失败测试：build_state_history 纯函数（首条即切换、相邻相同不算、末尾连续计数、空序列）；payload 契约（refresh_once 后 state_history.switches 非空且含最新状态；decision=None 时 state_history 为 None）。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 最小实现。
- [ ] Step 4: 全量测试通过（含既有 scheduler/api 测试回归）。
- [ ] Step 5: 提交 `feat: expose state history timeline in payload`。

---

### Task 3: 前端时间轴渲染

**Files:**
- Modify: `static/index.html`（新增状态历史卡片）
- Modify: `static/assets/app.js`（`renderStateHistory`；无 `state_history` 时隐藏）
- Modify: `static/assets/style.css`（时间轴样式 + 640px 断点）
- Test: `tests/test_state_history_static.py`

**前端规则:**
- 切换记录：日期时间 + 状态中文名 + 仓位区间 + 倍率 + 原因（reasons 首条）。
- 当前持续时长：`当前状态已持续 N 次刷新`（约 N×15 分钟）。
- 无切换记录时显示"暂无状态切换记录"。

- [ ] Step 1: 写失败测试（静态契约）。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 最小实现。
- [ ] Step 4: 全量测试通过；刷新真实快照；浏览器核验桌面与手机端。
- [ ] Step 5: 提交 `feat: render state history timeline on dashboard`。

---

### Task 4: 三份文档同步与最终验收

- [ ] roadmap：P0.3 ✅ + 交付记录 + 提交哈希 + 实施顺序划掉。
- [ ] CONTEXT.md：数据流补充 state_history 表与组装；文件地图新增 state_history.py；界面约定补充时间轴。
- [ ] MEMORY.md：记录"状态历史每次刷新入库、仅展示切换事件、收益统计后续迭代"。
- [ ] 全量验收：`pytest -q`、`git diff --check`、`git status --short`。

---

## Plan Self-Review

| 需求项 | 覆盖位置 |
| --- | --- |
| 最近 90 天状态变化记录 | Task 1 表 + since 过滤 |
| 切换日期与原因、仓位、倍率 | Task 2 switches + reasons |
| 状态持续时间与切换频率 | Task 2 current_duration_ticks |
| 首次只做切换记录展示 | Global Constraints + Task 3（无收益统计） |
| 不改变决策规则 | Task 2 防回归断言 + 既有 decision 测试 |
