# P0.1 阈值距离与趋势矩阵 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将信号拆解从"已触发/未触发"升级为阈值距离矩阵：每条规则展示当前值、触发条件、剩余距离与近 5 日方向；数据源不可用时标注"未参与本次判断"。不改变任何决策输出。

**Architecture:** 新增纯函数服务 `app/services/explanation.py` 计算距离与方向（读取 `rules.thresholds`，不复用也不修改 `decision.py`）；`app/scheduler.py` 仅做接线，把矩阵写入 `market["qqq"]["threshold_matrix"]`；前端 `app.js` 把矩阵渲染为表格注入既有 `#reasons` 容器，保留现有文字解释作为表格下方补充。

**Tech Stack:** Python 3 + pydantic（后端）、原生 HTML/CSS/JavaScript（前端）、pytest（单元测试 + 静态契约测试）。

## Global Constraints

- 禁止修改 `app/services/decision.py`、`config/default_rules.json` 中的阈值、仓位范围与定投倍率；`scheduler.py` 仅允许接线改动（保存 VIX bars、调用新服务、写入 payload 字段）。
- 距离语义统一为"距离触发还差多少"：`distance > 0` 未触发，`distance ≤ 0` 已触发。RSI 超卖 = `当前值 − 阈值`；回撤 = `当前值 − (−12)`（个百分点）；VIX = `30 − 当前值`；成交量 = `2 − 当前倍数`。
- 方向判定：最近一个交易日值对比 5 个交易日前的值，`|差值| ≤ epsilon` 记为平稳；epsilon 固定为 RSI 1.0、回撤 0.5 个百分点、VIX 0.5、成交量 0.1 倍。
- 方向基于日线正式收盘序列计算（不含盘中估算），前端须注明；当前值可为盘中估算，两者允许微小不一致。
- 任一输入缺失（指标为 `None`、bars 不足、VIX 源失败）时该行 `available=false`，前端显示 `--` 与"未参与本次判断"，绝不伪造数值或方向。
- 涨跌配色固定：`#3DDC97`（绿）/ `#F0656B`（红）；暗色终端风格、等宽字体不变；640px 断点下表格可读（横向滚动或换行堆叠），不依赖悬停。
- 前端必须容忍旧快照无 `threshold_matrix` 字段（Pages 缓存期间），此时保留现有文字拆解。
- 每个 Task 严格 TDD：先写失败测试并确认失败，再做最小实现，全部通过后提交；提交前运行 `git diff --check`。

---

### Task 1: 距离与方向纯逻辑服务

**Files:**
- Add: `app/services/explanation.py`
- Modify: `app/models.py`（新增行模型）
- Test: `tests/test_explanation.py`

**Interfaces:**

```python
# app/models.py 新增
class ThresholdDistanceRow(BaseModel):
    rule: str                    # "rsi2_oversold" | "rsi6_oversold" | "drawdown_risk" | "vix_high" | "volume_ratio_high"
    label: str                   # 中文名，VIX 必须为 "VIX（恐慌指数）"
    current: float | None        # None = 数据不可用
    condition: str               # "≤ 15" / "≤ -12%" / "≥ 30" / "≥ 2 倍"
    distance: float | None       # 距触发差值；≤0 表示已触发
    unit: str                    # "点" | "个百分点" | "倍"
    direction: str | None        # "rising"/"falling"/"flat"（回撤用 "widening"/"narrowing"/"flat"）；None = 历史不足
    available: bool
    note: str | None             # 不可用时为 "未参与本次判断"

# app/services/explanation.py
def distance_to_trigger(current: float | None, threshold: float, kind: str) -> float | None: ...
def five_day_direction(series: Sequence[float | None], epsilon: float) -> str | None: ...
def build_threshold_matrix(
    qqq_bars: list[PriceBar] | None,
    vix_bars: list[PriceBar] | None,
    indicators: IndicatorSet,
    rules: RuleConfig,
) -> list[ThresholdDistanceRow]: ...
```

- [ ] **Step 1: Write the failing test**

`tests/test_explanation.py` 覆盖以下用例（全部使用构造数据，不触网）：

```python
def test_distances_match_spec_examples() -> None:
    # RSI(2)=75.88 → 60.88 点；RSI(6)=49.41 → 19.41 点；
    # 回撤=-7.8 → 4.2 个百分点；VIX=16.01 → 13.99；成交量=1.26 → 0.74 倍
def test_triggered_rule_has_non_positive_distance() -> None:  # 如 RSI(2)=10 → -5.0
def test_direction_uses_five_trading_day_delta_with_epsilon() -> None:
    # 上升/下降/平稳三态；差值 ≤ epsilon 判平稳
def test_drawdown_direction_labels_are_widening_or_narrowing() -> None:
def test_missing_indicator_marks_row_unavailable() -> None:
    # vix=None → available=False, note="未参与本次判断", distance=None, direction=None
def test_matrix_reads_thresholds_from_rules_not_hardcoded() -> None:
    # 传入自定义 thresholds，距离随之变化
```

QQQ 四项指标的历史序列测试：用 30 根合成 `PriceBar` 验证 `build_threshold_matrix` 通过截取 `bars[:-k]`（k=0..4，注意 k=0 时取完整列表）重算 RSI/回撤/成交量序列得到方向。

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_explanation.py -q`
Expected: FAIL（模块与模型尚不存在，ImportError）。

- [ ] **Step 3: Write minimal implementation**

- `models.py` 增加 `ThresholdDistanceRow`。
- `explanation.py`：`distance_to_trigger` 按 kind（`le` / `ge`）计算有符号距离并保留两位小数；`five_day_direction` 取序列首末值差并与 epsilon 比较，序列少于 2 个有效值返回 `None`；`build_threshold_matrix` 从 `rules.thresholds` 读阈值，生成顺序固定的 5 行（RSI(2)、RSI(6)、回撤、VIX、成交量）。

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS（全量回归，确认 `test_decision.py` 等未受影响）。

- [ ] **Step 5: Commit**

```powershell
git add app/services/explanation.py app/models.py tests/test_explanation.py
git diff --check
git commit -m "feat: add threshold distance and 5-day direction service"
```

---

### Task 2: 调度器接线与 payload 契约

**Files:**
- Modify: `app/scheduler.py`（仅接线：保留 `vix_bars` 引用、调用 `build_threshold_matrix`、写入 `market["qqq"]["threshold_matrix"]`，用 `[row.model_dump() for row in rows]` 序列化）
- Test: `tests/test_threshold_matrix_payload.py`

**Interfaces:** `collect_dashboard_payload(previous)` 签名不变；输出契约新增 `market["qqq"]["threshold_matrix"]` 为 5 个 dict 的列表，键与 `ThresholdDistanceRow` 一致。

- [ ] **Step 1: Write the failing test**

沿用现有注入惯例（参考 `tests/test_scheduler.py` 的 `collect=` 注入与 `refresh_once` 模式），对 `collect_dashboard_payload` 用 monkeypatch 替换 `app.scheduler.fetch_daily_bars` / `fetch_quote` / `fetch_fear_greed` / `load_macro_events`：

```python
def test_payload_contains_threshold_matrix_rows() -> None:
    # 合成 ≥210 根 QQQ bars 与 30 根 VIX bars
    # 断言 market["qqq"]["threshold_matrix"] 长度为 5，
    # 且 rule 键集合 == {"rsi2_oversold","rsi6_oversold","drawdown_risk","vix_high","volume_ratio_high"}
def test_vix_source_failure_marks_vix_row_unavailable() -> None:
    # VIX bars 返回 (None, failed status) → 该行 available=False、note="未参与本次判断"，其余 4 行正常
def test_decision_fields_unchanged_by_matrix() -> None:
    # 同一组指标下 decision.state/allocation/dca_multiplier 与接入矩阵前一致（防回归）
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_threshold_matrix_payload.py -q`
Expected: FAIL（payload 中尚无 `threshold_matrix`）。

- [ ] **Step 3: Write minimal implementation**

在 `collect_dashboard_payload` 中：VIX 分支同时保存 `vix_bars = bars`；在 `qqq_bars` 分支内 `market["qqq"]["indicators"] = ...` 之后调用 `build_threshold_matrix(qqq_bars, vix_bars, indicators, load_rule_config())` 并写入 `market["qqq"]["threshold_matrix"]`。不改动 `evaluate_decision` 调用与其入参。

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS（含 `test_scheduler.py`、`test_scheduler_runtime.py`、`test_api.py` 等既有调度/快照测试）。

- [ ] **Step 5: Commit**

```powershell
git add app/scheduler.py tests/test_threshold_matrix_payload.py
git diff --check
git commit -m "feat: expose threshold distance matrix in dashboard payload"
```

---

### Task 3: 前端矩阵渲染与响应式样式

**Files:**
- Modify: `static/assets/app.js`
- Modify: `static/assets/style.css`
- Test: `tests/test_threshold_matrix_static.py`

**Interfaces:** `app.js` 新增 `renderThresholdMatrix(rows)`（返回 HTML 字符串）并在 `renderDashboard` 中注入 `#reasons` 顶部：

- 表头：`规则 | 当前值 | 触发条件 | 距离 | 近 5 日方向`；
- 距离格式：数值 + 单位（`60.88 点`、`4.2 个百分点`、`0.74 倍`），`distance ≤ 0` 时显示 `已触发`；
- 方向中文化：rising→上升、falling→下降、flat→平稳、widening→扩大、narrowing→收窄；方向为 `null` 显示 `数据不足`；
- `available=false` 行：当前值/距离显示 `--`，方向列替换为 `未参与本次判断`（样式 `bad`）；
- `threshold_matrix` 缺失（旧快照）时回退为现有 `formatSignalBreakdown` 文字列表；存在时表格之后仍保留原文字拆解作为解释；
- 配色：已触发的风险行数值用 `#F0656B`，已触发的超卖机会行用 `#3DDC97`，方向与单位用 `--muted`；表格下方加注 `方向基于最近 5 个交易日收盘值`。

- [ ] **Step 1: Write the failing test**

```python
def test_threshold_matrix_dom_contract_and_styles() -> None:
    script = Path("static/assets/app.js").read_text(encoding="utf-8")
    styles = Path("static/assets/style.css").read_text(encoding="utf-8")
    assert "renderThresholdMatrix" in script
    assert "threshold-matrix" in script
    assert "近 5 日方向" in script and "触发条件" in script
    assert "未参与本次判断" in script
    assert "扩大" in script and "收窄" in script
    assert ".threshold-matrix" in styles
    assert "@media(max-width:640px)" in styles and "threshold-matrix" in styles  # 移动端规则
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_threshold_matrix_static.py -q`
Expected: FAIL（函数与样式类不存在）。

- [ ] **Step 3: Write minimal implementation**

- `app.js`：实现 `renderThresholdMatrix` 与注入逻辑（含旧快照回退分支）。
- `style.css`：追加一行式规则（与现有压缩风格一致）：`.threshold-matrix{width:100%;border-collapse:collapse;font-size:13px}`，单元格 `border-bottom:1px solid var(--line)`、数字列右对齐（`text-align:right`）、表头 `--muted`；移动端断点内为表格外层 `display:block;overflow-x:auto` 保证 5 列可读，或将"近 5 日方向"折行为第二行（二选一，以 375px 宽度下无横向截断为准）。

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS。随后人工核验：`.\.venv\Scripts\python.exe -m scripts.refresh_dashboard` 生成新快照，`.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000` 打开页面，分别在桌面宽度与 375px 手机宽度（DevTools 模拟）确认表格可读、配色正确、VIX 不可用场景标注无误。

- [ ] **Step 5: Commit**

```powershell
git add static/assets/app.js static/assets/style.css tests/test_threshold_matrix_static.py
git diff --check
git commit -m "feat: render threshold distance matrix on dashboard"
```

---

### Task 4: 文档同步与最终验收

**Files:**
- Modify: `CONTEXT.md`（"重要界面约定"与数据流处补充 `threshold_matrix` 字段）
- Modify: `MEMORY.md`（补充"信号拆解已升级为距离矩阵；方向基于日线收盘"条目）

- [ ] **Step 1: 更新两份协作文档**（按 `AGENTS.md` 第 55–59 行的维护边界，只写长期事实，不写过程）。
- [ ] **Step 2: 全量验收**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
git status --short
```

Expected: 全部通过；无 `static/data/dashboard.json` 或 SQLite 文件进入暂存区。

- [ ] **Step 3: Commit**

```powershell
git add CONTEXT.md MEMORY.md
git commit -m "docs: record threshold distance matrix contract"
```

---

## Plan Self-Review

**Spec 覆盖核对（对照 roadmap P0.1 验收要点与本次需求）：**

| 需求项 | 覆盖位置 |
| --- | --- |
| 5 行规则、当前值/触发条件/距离/方向四列 | Task 1 行模型 + Task 3 表头 |
| 距离示例数值（60.88 / 19.41 / 4.2pp / 13.99 / 0.74） | Task 1 Step 1 直接以 spec 示例为断言 |
| 不修改 `decision.py` 阈值/仓位/倍率 | Global Constraints + Task 2 回归断言 `test_decision_fields_unchanged_by_matrix` |
| 数据源不可用标注"未参与本次判断" | Task 1 `available/note`、Task 2 VIX 失败用例、Task 3 渲染规则 |
| 桌面 + 手机可读 | Task 3 移动端 CSS 断言 + 人工 375px 核验 |
| 暗色风格、`#3DDC97`/`#F0656B` | Task 3 配色约定；未引入新主色 |
| TDD、pytest、`git diff --check` | 每个 Task 的 Step 1–5 |
| 新后端逻辑在 `app/services/`/`app/models.py` | Task 1；`scheduler.py` 仅接线已在约束中声明 |

**Placeholder 检查:** 无待定项；epsilon、距离公式、行键名、中文文案均已固定为确定值。

**类型一致性检查:** `current/distance/direction` 均允许 `None`，后端 `float | None` → JSON `null` → 前端 `v==null` 判断，链路与现有 `number()`/`metric()` 辅助函数约定一致；`market` 为自由 dict，旧快照反序列化不受影响（Task 3 已含回退分支）。

**已知取舍与风险:**
1. 路线图表格仅含 5 行：200 日均线（二元穿越，无连续距离语义）与恐贪指数（不在风险路径内）按 spec 不纳入矩阵；现有文字拆解仍保留恐贪不可用说明，如需补充可作为后续迭代。
2. 方向用"5 个交易日前 vs 最新收盘"的两点比较而非斜率拟合，简单透明、与 spec 的三态输出匹配；epsilon 为经验值，若上线后方向抖动明显只需改 `explanation.py` 常量并更新测试。
3. 方向序列不含盘中估算，与"当前值（可能盘中估算）"存在分钟级不一致，已通过表格注记声明，符合"不伪造实时性"原则。
4. GitHub Pages 缓存期间线上 `dashboard.json` 可能暂无 `threshold_matrix`，前端回退逻辑保证过渡期页面不空白。
