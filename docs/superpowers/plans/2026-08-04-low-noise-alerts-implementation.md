# P0.5 低噪声提醒 Implementation Plan

**Goal:** 只在有决策意义的变化时产生页面内提醒，不接入外部通知渠道、不对每次 15 分钟刷新发提醒。提醒类型：五档状态切换、指标进入阈值附近、两项及以上风险条件同时触发（defensive 状态）、关键数据源持续失败、高影响事件（FOMC/CPI/非农）临近。

**Architecture:** 新增纯函数服务 `app/services/alerts.py`：`build_alerts(previous, current)` 对比相邻两次快照产出 `Alert` 列表，用"进入状态/进入附近/由好变坏"的边沿触发 + 与 `previous.alerts` 的 key 去重保证低噪声；`refresh_once` 组装 payload 顶层 `alerts`；前端新增页面内提醒条。

## Global Constraints

- 不修改 `app/services/decision.py` 与规则配置；multiple_risks 用 `state == defensive`（决策已定义防御 = ≥2 风险）判定，不复制风险逻辑。
- 提醒只写 payload 顶层 `alerts` 并在页面内展示；绝不推送、不持久化（随快照自然流转）。
- 触发条件均为边沿事件（与上次快照对比），同一 key 已在上次 alerts 中则不重复。
- 每个 Task 严格 TDD；完成后按 AGENTS.md 同步三份文档。

---

### Task 1: alerts 服务

**Files:**
- Modify: `app/models.py`（`Alert`）
- Add: `app/services/alerts.py`
- Test: `tests/test_alerts.py`

**模型:**

```python
class Alert(BaseModel):
    key: str       # 去重键，如 "state_switch:constructive" / "near:vix_high"
    kind: str      # state_switch | near_threshold | multiple_risks | source_stale | event_approaching
    title: str
    detail: str
```

**触发条件（边沿 + 去重，previous 为 None 时除事件类外不提醒）:**

| kind | 触发 | 缓冲/定义 |
| --- | --- | --- |
| state_switch | current.state != previous.state | — |
| near_threshold | 本次距离 ≤ 缓冲 且 上次距离 > 缓冲（进入附近） | rsi2/rsi6: 5.0；drawdown: 2.0pp；vix: 3.0；volume: 0.3 |
| multiple_risks | current.state == defensive 且 previous.state != defensive | — |
| source_stale | 本次 unavailable 且 上次同源 unavailable（持续失败） | — |
| event_approaching | events 中 kind in (fomc, nfp, cpi) 且距今天 ≤ 3 天 | 去重键含日期 |

- [ ] Step 1: 写失败测试（约 10 个用例）：五类各覆盖触发与不触发、去重、previous=None、缓冲边界（恰好等于缓冲算附近）。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 最小实现。
- [ ] Step 4: `pytest -q` 全量通过。
- [ ] Step 5: 提交 `feat: add low-noise alert service`。

---

### Task 2: payload 接线

**Files:**
- Modify: `app/models.py`（`DashboardPayload.alerts`）
- Modify: `app/scheduler.py`（`refresh_once` 组装 alerts，与 state_history 同模式）
- Test: `tests/test_alerts_payload.py`

- [ ] Step 1: 写失败测试：refresh_once 后 payload.alerts 存在且与 build_alerts 独立重算一致；无变化时 alerts 为空列表；decision 缺失不阻断 source/event 类提醒。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 最小实现。
- [ ] Step 4: 全量测试通过（含既有 scheduler/api 回归）。
- [ ] Step 5: 提交 `feat: expose alerts in dashboard payload`。

---

### Task 3: 前端提醒条

**Files:**
- Modify: `static/index.html`（`#alert-banner`）
- Modify: `static/assets/app.js`（`renderAlerts`；无 alerts/空列表时隐藏）
- Modify: `static/assets/style.css`（横幅样式 + 640px 断点）
- Test: `tests/test_alerts_static.py`

**前端规则:**
- 每条提醒：`kind` 徽标 + title + detail；横幅注明"仅页面内提醒，不推送"。
- 空列表/缺失字段时隐藏整个横幅。

- [ ] Step 1: 写失败测试（静态契约）。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 最小实现。
- [ ] Step 4: 全量测试通过；刷新真实快照（构造一次状态切换核验渲染）；浏览器核验桌面与手机端。
- [ ] Step 5: 提交 `feat: render alert banner on dashboard`。

---

### Task 4: 三份文档同步与最终验收

- [ ] roadmap：P0.5 ✅ + 交付记录 + 提交哈希 + 实施顺序划掉。
- [ ] CONTEXT.md：payload 新增 `alerts` 字段、触发条件表、界面约定补充提醒条。
- [ ] MEMORY.md：记录提醒触发条件为产品语义（边沿事件 + key 去重），改动须授权。
- [ ] 全量验收：`pytest -q`、`git diff --check`、`git status --short`。

---

## Plan Self-Review

| 需求项 | 覆盖位置 |
| --- | --- |
| 状态切换提醒 | Task 1 state_switch |
| 指标进入阈值附近 | Task 1 near_threshold（缓冲表） |
| 两项及以上风险触发 | Task 1 multiple_risks（复用 defensive 语义） |
| 关键数据源持续失败 | Task 1 source_stale |
| 事件临近（FOMC/CPI/非农） | Task 1 event_approaching |
| 不接外部通知、不每次刷新提醒 | Global Constraints + 边沿触发 + key 去重 + 页面内渲染 |
| 不改变决策规则 | 无 decision.py 改动 + 复用既有语义 |
