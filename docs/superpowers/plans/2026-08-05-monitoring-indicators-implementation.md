# Monitoring Indicators Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a decision-support monitoring area that highlights CNN sentiment, QQQ/QQQE breadth and trend, existing sector assets, volatility, rates, and the dollar without changing the formal five-state decision.

**Architecture:** Extend the CNN adapter with optional detail fields, compute a typed top-level `monitoring` payload in a new pure service, and attach it during the existing refresh. The static frontend renders a persistent four-card summary followed by four mutually exclusive accordion groups; it never recalculates monitoring labels or alters `decision`.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, yfinance, httpx, SQLite snapshots, pytest, native HTML/CSS/JavaScript, Lightweight Charts already present in the project.

## Global Constraints

- Do not modify `app/services/decision.py`, `config/default_rules.json`, five-state meanings, allocation ranges, or DCA multipliers.
- Do not add symbols, external data sources, JavaScript packages, build tooling, broker integration, or personal-asset storage.
- Preserve the existing CNN current-score behavior; history and seven factors are optional additive fields.
- Reuse QQQ, QQQE, XLK, SMH, XLE, XLF, VIX, VIX3M, `^TNX`, and `DX-Y.NYB` bars already collected by the scheduler.
- New monitoring labels are descriptive evidence only; they must not become formal trade instructions.
- Preserve the terminal visual language, `#3DDC97` up color, `#F0656B` down color, responsive behavior, and explicit unavailable/stale copy.
- Execute implementation with `gpt-5.6-terra`, using at most two subagents only for tasks without shared-file conflicts.
- Run tests from the repository worktree with `./.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider`; the current full baseline is 186 tests.

---

## File Map

- Create `app/services/monitoring.py`: pure metric calculations, summary construction, four fixed groups, and stale fallback.
- Create `tests/test_monitoring.py`: service calculations, group contract, summaries, color semantics, and partial-data behavior.
- Create `tests/test_monitoring_payload.py`: scheduler and snapshot integration tests.
- Create `tests/test_monitoring_static.py`: HTML, JavaScript, accordion, accessibility, responsive, and old-payload contracts.
- Modify `app/models.py`: typed monitoring payload models and optional `DashboardPayload.monitoring`.
- Modify `app/providers/cnn_fear_greed.py`: tolerant optional history/factor parsing.
- Modify `app/scheduler.py`: retain fetched bars by key and attach monitoring after existing QQQ evidence is computed.
- Modify `app/services/dashboard.py`: carry monitoring through payload construction and previous-snapshot fallback.
- Modify `static/index.html`: monitoring container after the QQQ/macro hero grid.
- Modify `static/assets/app.js`: monitoring renderers and session-scoped accordion state.
- Modify `static/assets/style.css`: summary, detail visualizations, mobile 2×2 summary, and accessible accordion styles.
- Restore/create `docs/investment-system.md` and `docs/product-roadmap.md` from `master`, then modify the roadmap plus `CONTEXT.md` and `MEMORY.md`: completion record and durable contracts.

---

### Task 1: Extend CNN sentiment data without breaking the current score

**Files:**
- Modify: `app/providers/cnn_fear_greed.py`
- Modify: `tests/test_providers.py`

**Interfaces:**
- Consumes: CNN JSON object already loaded in `fetch_fear_greed(client)`.
- Produces: `FearGreedReading` with unchanged required `score`, `rating`, `observed_at` plus optional comparisons, `history`, and `factors`.

- [ ] **Step 1: Write failing provider tests**

Add a response fixture that contains the current object, optional comparison fields, a historical series, and the seven known factor keys. Assert the existing three fields and the new optional values:

```python
def test_fear_greed_parses_optional_monitoring_details() -> None:
    payload = {
        "fear_and_greed": {
            "score": 58.4,
            "rating": "greed",
            "timestamp": "2026-08-04T20:00:00+00:00",
            "previous_close": 46.0,
            "previous_1_week": 38.0,
            "previous_1_month": 33.0,
            "previous_1_year": 64.0,
        },
        "fear_and_greed_historical": {
            "data": [[1785800000000, 46.0], [1785886400000, 58.4]]
        },
        "market_momentum_sp500": {"score": 81.0, "rating": "extreme greed"},
    }
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reading, status = fetch_fear_greed(client)
    assert status.available is True
    assert reading.score == 58
    assert reading.previous_close == 46.0
    assert reading.history[-1].score == 58.4
    assert reading.factors[0].key == "market_momentum"
```

Add tests for: current-only payload (`history == ()`, `factors == ()`); HTTP 418 returning unavailable; malformed required current fields returning unavailable; malformed optional history/factors being skipped independently; and all seven source keys mapping to stable English keys and Chinese labels. Accept historical rows only in the two shapes covered by fixtures: `[timestamp_ms, score]` and `{x: timestamp_ms, y: score}`.

- [ ] **Step 2: Run the new tests and observe RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_providers.py -q
```

Expected: failures because the new dataclasses and fields do not exist.

- [ ] **Step 3: Implement tolerant optional parsing**

Add immutable value types and this fixed source-key map:

```python
_FACTOR_META = {
    "market_momentum_sp500": ("market_momentum", "市场动量"),
    "stock_price_strength": ("stock_price_strength", "股价强度"),
    "stock_price_breadth": ("stock_price_breadth", "市场宽度"),
    "put_call_options": ("put_call_options", "期权情绪"),
    "market_volatility_vix": ("market_volatility", "市场波动率"),
    "junk_bond_demand": ("junk_bond_demand", "垃圾债需求"),
    "safe_haven_demand": ("safe_haven_demand", "避险需求"),
}
```

```python
@dataclass(frozen=True)
class FearGreedPoint:
    observed_at: datetime
    score: float

@dataclass(frozen=True)
class FearGreedFactor:
    key: str
    label: str
    score: float
    rating: str | None = None

@dataclass(frozen=True)
class FearGreedReading:
    score: int
    rating: str
    observed_at: datetime
    previous_close: float | None = None
    previous_week: float | None = None
    previous_month: float | None = None
    previous_year: float | None = None
    history: tuple[FearGreedPoint, ...] = ()
    factors: tuple[FearGreedFactor, ...] = ()
```

Use `_optional_float`, `_parse_history`, and `_parse_factors` helpers. Skip malformed optional rows or factors, but preserve the existing outer exception behavior when required current fields are invalid. Map only the seven confirmed CNN keys; ignore unknown response keys.

- [ ] **Step 4: Run provider tests and regression tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_providers.py tests/test_macro_calendar.py -q
```

Expected: PASS; the existing current-score and unavailable-source tests remain unchanged.

- [ ] **Step 5: Commit Task 1**

```powershell
git add app/providers/cnn_fear_greed.py tests/test_providers.py
git commit -m "feat: parse optional CNN monitoring details"
```

---

### Task 2: Define the monitoring contract and pure calculation service

**Files:**
- Modify: `app/models.py`
- Create: `app/services/monitoring.py`
- Create: `tests/test_monitoring.py`

**Interfaces:**
- Consumes: `Mapping[str, Sequence[PriceBar] | None]`, current `market` cards, `FearGreedReading | None`, events, source statuses, timestamp, and `MonitoringPayload | None` from the previous snapshot.
- Produces: `build_monitoring(*, generated_at: datetime, bars_by_key: Mapping[str, Sequence[PriceBar] | None], market: Mapping[str, dict[str, object]], fear_greed: FearGreedReading | None, events: Sequence[MacroEvent], sources: Mapping[str, SourceStatus], previous: MonitoringPayload | None = None) -> MonitoringPayload` with exactly four summary cards and four fixed group keys.
- Fixed group contents and order:
  - `sentiment_volatility`: metrics `cnn_score`, `vix`, `vix3m`; details `comparisons`, `history`, `factors`, `term_ratio`, `term_status`.
  - `core_breadth`: metrics `qqq`, `qqqe`, `ma200`, `drawdown`, `breadth_rs_5d`, `breadth_rs_20d`.
  - `sector_rotation`: metrics `xlk`, `smh`, `xle`, `xlf`.
  - `macro_defensive`: metrics `treasury_10y`, `dollar_index`; details `events`.

- [ ] **Step 1: Write failing model and metric tests**

Define test helpers producing 21 dated `PriceBar` values. Cover percentage calculations, insufficient history, units, and fixed group order:

```python
def test_build_market_metric_exposes_latest_and_changes() -> None:
    metric = build_market_metric("qqq", "QQQ", bars([100.0] * 20 + [105.0]), unit="USD", mode="percent", epsilon=DIRECTION_EPSILON["price_pct"])
    assert metric.current == 105.0
    assert metric.change_1d == 5.0
    assert metric.momentum_20d == 5.0
    assert metric.change_unit == "%"
    assert metric.as_of == date(2026, 8, 4)

def test_build_monitoring_has_fixed_reference_groups() -> None:
    result = build_monitoring(**monitoring_inputs())
    assert list(result.groups) == [
        "sentiment_volatility",
        "core_breadth",
        "sector_rotation",
        "macro_defensive",
    ]
    assert [card.key for card in result.summary] == [
        "sentiment", "core_trend", "breadth", "volatility"
    ]
```

Also assert that missing values remain `None`, not zero, and monitoring summaries never contain “买入”, “卖出”, “加仓”, or “减仓”.

- [ ] **Step 2: Run Task 2 tests and observe RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_monitoring.py -q
```

Expected: import failures for monitoring models and service.

- [ ] **Step 3: Add typed payload models**

Add Pydantic models with these exact fields:

```python
from datetime import date, datetime

class MonitoringPoint(BaseModel):
    observed_at: datetime
    value: float

class MonitoringFactor(BaseModel):
    key: str
    label: str
    score: float
    rating: str | None = None
    change: float | None = None
    tone: Literal["positive", "negative", "warning", "neutral", "unavailable"]

class MonitoringDetails(BaseModel):
    comparisons: dict[str, float | None] = Field(default_factory=dict)
    history: list[MonitoringPoint] = Field(default_factory=list)
    factors: list[MonitoringFactor] = Field(default_factory=list)
    term_ratio: float | None = None
    term_status: str | None = None
    events: list[MacroEvent] = Field(default_factory=list)

class MonitoringMetric(BaseModel):
    key: str
    label: str
    current: float | None = None
    unit: str | None = None
    change_1d: float | None = None
    change_unit: str | None = None
    direction_5d: str | None = None
    momentum_20d: float | None = None
    momentum_unit: str | None = None
    as_of: date | None = None
    tone: Literal["positive", "negative", "warning", "neutral", "unavailable"] = "neutral"
    display_status: str = "数据正常"
    data_status: Literal["available", "partial", "unavailable"] = "available"
    available: bool = True
    stale: bool = False
    note: str | None = None

class MonitoringSummary(BaseModel):
    key: str
    label: str
    display_value: str
    status: str
    tone: Literal["positive", "negative", "warning", "neutral", "unavailable"]
    data_status: Literal["available", "partial", "unavailable"] = "available"
    available: bool = True
    stale: bool = False
    as_of: date | None = None

class MonitoringGroup(BaseModel):
    key: str
    label: str
    status: str
    data_status: Literal["available", "partial", "unavailable"] = "available"
    available: bool = True
    stale: bool = False
    metrics: list[MonitoringMetric] = Field(default_factory=list)
    details: MonitoringDetails = Field(default_factory=MonitoringDetails)

class MonitoringPayload(BaseModel):
    generated_at: datetime
    summary: list[MonitoringSummary]
    groups: dict[str, MonitoringGroup]
```

Add `monitoring: MonitoringPayload | None = None` to `DashboardPayload`.

- [ ] **Step 4: Implement exact metric calculations and group builders**

Use the following calculation rules in `monitoring.py`: `change_1d = (last / previous - 1) * 100` for ETF/index metrics and `last - previous` for point metrics; 5-day direction compares the last close with `bars[-6]`; 20-day momentum compares the last close with `bars[-21]`. A direction is flat when the absolute change is at most the configured epsilon. Declare `DIRECTION_EPSILON = {"price_pct": 0.5, "cnn_points": 1.0, "vol_points": 0.5, "macro_points": 0.1}`.

```python
def _change(current: float, base: float, mode: str) -> float:
    value = (current / base - 1.0) * 100 if mode == "percent" else current - base
    return round(value, 2)

def _direction(value: float | None, epsilon: float) -> str | None:
    if value is None:
        return None
    if value > epsilon:
        return "rising"
    if value < -epsilon:
        return "falling"
    return "flat"

def build_market_metric(key: str, label: str, bars: Sequence[PriceBar] | None,
                        *, unit: str, mode: Literal["percent", "points"],
                        epsilon: float) -> MonitoringMetric:
    if not bars:
        return MonitoringMetric(key=key, label=label, available=False,
                                tone="unavailable", display_status="不可用",
                                data_status="unavailable")
    current = bars[-1].close
    change_1d = _change(current, bars[-2].close, mode) if len(bars) >= 2 else None
    change_5d = _change(current, bars[-6].close, mode) if len(bars) >= 6 else None
    momentum_20d = _change(current, bars[-21].close, mode) if len(bars) >= 21 else None
    return MonitoringMetric(
        key=key, label=label, current=current, unit=unit,
        change_1d=change_1d, change_unit="%" if mode == "percent" else unit,
        direction_5d=_direction(change_5d, epsilon),
        momentum_20d=momentum_20d,
        momentum_unit="%" if mode == "percent" else unit,
        as_of=bars[-1].day,
    )
```

Implement `build_monitoring` with the exact keyword-only signature already listed under Interfaces. It calls four isolated `_build_*_group` helpers inside separate `try` blocks; a failed helper returns only that group with `data_status="unavailable"`. Build summaries only from the corresponding completed group. If required summary inputs are missing, set `status="部分数据缺失"`, `data_status="partial"`, and do not emit a direction label. Reuse existing `market.qqq.trend` and `market.qqq.breadth` labels instead of duplicating their rules. Use `tone="negative"` for rising VIX risk and `tone="positive"` for falling VIX; all other semantic tones are assigned in Python.

- [ ] **Step 5: Add partial-data and stale-fallback tests**

Test a missing CNN reading, one missing sector series, insufficient 20-day bars, each group builder raising independently, all groups unavailable, and a previous metric reused after source failure. The reused metric must retain its original `as_of`, set `stale=True`, `data_status="partial"`, and never produce a fresh direction from missing bars.

- [ ] **Step 6: Run Task 2 tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_monitoring.py tests/test_dashboard.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```powershell
git add app/models.py app/services/monitoring.py tests/test_monitoring.py
git commit -m "feat: add monitoring indicator service"
```

---

### Task 3: Attach monitoring to refresh, snapshots, and API payloads

**Files:**
- Modify: `app/scheduler.py`
- Modify: `app/services/dashboard.py`
- Create: `tests/test_monitoring_payload.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: the typed `build_monitoring` service from Task 2 and the existing previous `DashboardPayload`.
- Produces: API, SQLite, and `static/data/dashboard.json` snapshots containing optional top-level `monitoring`.

- [ ] **Step 1: Write failing scheduler integration tests**

Test that the scheduler retains every fetched series in `bars_by_key`, invokes monitoring only after QQQ trend/breadth fields exist, and serializes the result:

```python
def test_collect_dashboard_payload_attaches_monitoring(monkeypatch) -> None:
    monkeypatch.setattr("app.scheduler.build_monitoring", fake_build_monitoring)
    payload = collect_dashboard_payload(previous=None)
    assert payload.monitoring is not None
    assert payload.monitoring.groups["core_breadth"].key == "core_breadth"

def test_dashboard_api_preserves_monitoring_snapshot(tmp_path) -> None:
    repository.save_payload(payload_with_monitoring())
    response = TestClient(create_app(repository=repository)).get("/api/dashboard")
    assert response.json()["monitoring"]["summary"][0]["key"] == "sentiment"
```

- [ ] **Step 2: Run integration tests and observe RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_monitoring_payload.py tests/test_api.py -q
```

Expected: monitoring is absent from collected and serialized payloads.

- [ ] **Step 3: Retain bars and call the service**

In `collect_dashboard_payload`, initialize `bars_by_key = {}` and assign every successfully fetched `bars` under its scheduler key. After QQQ indicators, trend, breadth, and structural risk are populated, call `build_monitoring` with `previous.monitoring if previous else None`.

Add `mark_monitoring_stale(previous, generated_at) -> MonitoringPayload`, which clones every summary, group, and metric with `stale=True`, changes available data to `data_status="partial"`, and uses `status="部分数据缺失"` where a current summary cannot be recomputed. Extend `build_dashboard_payload` with explicit `monitoring: MonitoringPayload | None = None`; when the entire monitoring build raises and a previous payload exists, pass `mark_monitoring_stale(previous.monitoring, generated_at)`. When no previous monitoring exists, keep `monitoring=None` so the old-page behavior is to hide the section.

- [ ] **Step 4: Add degradation and decision-isolation assertions**

Assert that a missing CNN source affects only sentiment details, a missing XLK series affects only the XLK row, all monitoring unavailable still returns the formal decision, and the serialized `decision` equals the pre-monitoring decision fixture byte-for-byte. Add a JSON fixture without `monitoring` and assert `DashboardPayload.model_validate`, SQLite save/load, and `/api/dashboard` all accept it.

- [ ] **Step 5: Run scheduler/API regressions**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_monitoring_payload.py tests/test_scheduler.py tests/test_dashboard.py tests/test_api.py tests/test_decision.py -q
```

Expected: PASS with unchanged decision expectations.

- [ ] **Step 6: Commit Task 3**

```powershell
git add app/scheduler.py app/services/dashboard.py tests/test_monitoring_payload.py tests/test_api.py
git commit -m "feat: expose monitoring dashboard payload"
```

---

### Task 4: Add the monitoring summary and accessible accordion shell

**Files:**
- Modify: `static/index.html`
- Modify: `static/assets/app.js`
- Create: `tests/test_monitoring_static.py`

**Interfaces:**
- Consumes: optional `payload.monitoring` from Task 3.
- Produces: `#monitoring-section`, four summary cards, four fixed group buttons, and one visible detail region.

- [ ] **Step 1: Write failing static contract tests**

```python
def test_monitoring_container_follows_core_hero() -> None:
    html = Path("static/index.html").read_text(encoding="utf-8")
    assert html.index('class="grid hero"') < html.index('id="monitoring-section"')
    assert html.index('id="monitoring-section"') < html.index('id="event-list"')

def test_monitoring_accordion_is_accessible() -> None:
    script = Path("static/assets/app.js").read_text(encoding="utf-8")
    assert "aria-expanded" in script
    assert "sessionStorage" in script
    assert "monitoring-open-group" in script
```

Also require `renderMonitoring`, `renderMonitoringSummary`, and `renderMonitoringGroups`, plus a guard that hides the section when `monitoring` is absent.

- [ ] **Step 2: Run static tests and observe RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_monitoring_static.py -q
```

Expected: missing container and renderers.

- [ ] **Step 3: Add the HTML shell at the confirmed B position**

Add one section immediately after the existing QQQ/macro hero grid:

```html
<section id="monitoring-section" class="card monitoring" hidden>
  <div class="monitoring-heading">
    <div><p class="label">市场监控摘要</p><h2>情绪 · 趋势 · 宽度 · 波动</h2></div>
    <span class="chip muted">监控佐证层</span>
  </div>
  <div id="monitoring-summary" class="monitoring-summary"></div>
  <div id="monitoring-groups" class="monitoring-groups"></div>
</section>
```

- [ ] **Step 4: Implement summary and mutually exclusive group buttons**

Implement fixed-order rendering from the payload. Use a button per group with `aria-expanded`, `aria-controls`, and a unique detail ID. Add `setOpenMonitoringGroup(key)` and `toggleMonitoringGroup(key)`; the setter writes the one allowed key to `sessionStorage`, closes every other detail region, and updates all `aria-expanded` attributes. Native buttons supply Enter/Space behavior. Do not calculate status or tone in JavaScript.

- [ ] **Step 5: Add old-payload and interaction tests**

Assert that `renderMonitoring(null)` hides and clears the section, summary cards render `partial`/`stale`/`unavailable` copy, the script contains the two named state functions, one session key, `aria-expanded`, and code that closes non-selected panels. Add a static assertion that `formatSignalBreakdown` no longer includes the CNN fear-greed sentence while its VIX threshold sentence remains.

- [ ] **Step 6: Run static tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_monitoring_static.py tests/test_static.py tests/test_signal_explanation_static.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```powershell
git add static/index.html static/assets/app.js tests/test_monitoring_static.py
git commit -m "feat: add monitoring summary accordion"
```

---

### Task 5: Render the expanded visual details and responsive styles

**Files:**
- Modify: `static/assets/app.js`
- Modify: `static/assets/style.css`
- Modify: `tests/test_monitoring_static.py`

**Interfaces:**
- Consumes: `MonitoringGroup.metrics` and group-specific `details` supplied by the backend.
- Produces: CNN gauge/history/factors, asset metric rows, volatility strip, data-state copy, desktop four-column summary, and mobile 2×2 summary.

- [ ] **Step 1: Extend static tests for each detail renderer**

Require these functions and visual contracts:

```python
def test_monitoring_detail_renderers_exist() -> None:
    script = Path("static/assets/app.js").read_text(encoding="utf-8")
    for name in (
        "renderSentimentVolatility",
        "renderCoreBreadth",
        "renderSectorRotation",
        "renderMacroDefensive",
        "renderMonitoringMetricRow",
    ):
        assert f"function {name}" in script
    assert "CNN 七项分因子" in script
    assert "部分数据缺失" in script
```

Add CSS assertions for `.monitoring-summary`, `.monitoring-group`, `.monitoring-factor-track`, `@media`, and `grid-template-columns:repeat(2` in the mobile rule.

- [ ] **Step 2: Run tests and observe RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_monitoring_static.py -q
```

- [ ] **Step 3: Implement group-specific rendering**

`renderSentimentVolatility` must render, in order: gauge/current status, four comparison cells, optional one-year SVG trend, seven factor bars, and VIX/VIX3M facts. Missing subsections render “不可用” independently; they do not hide the valid current score.

The other three renderers output compact rows containing name, latest value/unit, 1-day change, 5-day direction, 20-day momentum, timestamp, and unavailable/stale text. Use only the payload `tone`, `display_status`, and `data_status` fields for semantic classes and copy; never infer decision advice in JavaScript.

- [ ] **Step 4: Add isolated responsive CSS**

Prefix new classes with `monitoring-`. Desktop uses four summary columns and full factor/metric columns. At the existing mobile breakpoint, switch summaries to 2×2 and asset rows to essential columns. Provide `:focus-visible`, open/closed chevrons, and text/arrow labels so color is not the only signal.

- [ ] **Step 5: Run frontend contract regressions**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_monitoring_static.py tests/test_static.py tests/test_ixic_static.py tests/test_trend_static.py tests/test_attribution_static.py -q
```

Expected: PASS and no existing container or script contract removed.

- [ ] **Step 6: Commit Task 5**

```powershell
git add static/assets/app.js static/assets/style.css tests/test_monitoring_static.py
git commit -m "feat: render monitoring detail visualizations"
```

---

### Task 6: Validate real refresh, browser states, and documentation

**Files:**
- Create from `master`: `docs/investment-system.md`
- Create from `master`, then modify: `docs/product-roadmap.md`
- Modify: `CONTEXT.md`
- Modify: `MEMORY.md`
- Verify only: `static/data/dashboard.json` and local `data/*.sqlite` remain ignored.

**Interfaces:**
- Consumes: the completed monitoring payload and UI from Tasks 1–5.
- Produces: verified local artifact, documented contracts, and a clean commit without generated snapshots.

- [ ] **Step 1: Run focused and full automated tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_providers.py tests/test_monitoring.py tests/test_monitoring_payload.py tests/test_monitoring_static.py -q
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
git diff --check
```

Expected: all focused tests pass; the full count is greater than the 186-test baseline with zero failures; `git diff --check` prints nothing.

- [ ] **Step 2: Generate a real local snapshot**

```powershell
.\.venv\Scripts\python.exe -m scripts.refresh_dashboard
```

Inspect `static/data/dashboard.json` and confirm the four summary keys and four group keys exist. If CNN optional details are absent, confirm current score remains available and optional subsections are marked unavailable.

- [ ] **Step 3: Verify desktop and mobile behavior in a browser**

Start the local app:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Verify at desktop width and a mobile width near 390 px: B-position ordering, four-to-2×2 summary change, whole-card click, one-open-group rule, session restoration, keyboard activation, stale/unavailable copy, and unchanged IXIC/QQQ/original cards.

- [ ] **Step 4: Update the three mandatory documents**

The current `qqq-dashboard` worktree lacks the system-driven roadmap. Restore the authoritative pair before editing:

```powershell
git restore --source master -- docs/investment-system.md docs/product-roadmap.md
```

In `docs/product-roadmap.md`, add one completed “监控指标增强区” row after S2 with the changed-file summary, exact test count, commit hashes, and the statement that it is a reference layer that does not alter formal decisions. Update `CONTEXT.md` with the top-level monitoring contract, data flow, B-position UI, accordion/session behavior, and file map. Update `MEMORY.md` with the durable user preferences: existing assets only, latest plus 1d/5d/20d change, four fixed groups, and no decision coupling. Do not add temporary market values or debugging notes.

- [ ] **Step 5: Confirm generated data is not staged**

```powershell
git status --short
git check-ignore static/data/dashboard.json data/dashboard.sqlite
```

Expected: generated snapshot/database paths are ignored and absent from the staged file list.

- [ ] **Step 6: Commit Task 6**

```powershell
git add docs/investment-system.md docs/product-roadmap.md CONTEXT.md MEMORY.md
git commit -m "docs: record monitoring indicators delivery"
```

- [ ] **Step 7: Final verification after the documentation commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
git diff --check
git status --short --branch
```

Expected: zero test failures, no whitespace errors, and a clean worktree.
