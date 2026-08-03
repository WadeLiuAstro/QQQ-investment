# QQQ 定投与仓位决策仪表盘 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local FastAPI dashboard and a generated static mobile dashboard that provide transparent QQQ timing research signals, suggested 20%–60% allocation ranges, and DCA multipliers.

**Architecture:** A single Python domain layer fetches and persists market data, computes indicators, evaluates a deterministic five-state decision, and emits a typed dashboard payload. FastAPI reads the same payload locally; a refresh script writes the same assets for GitHub Pages. A backtest calls the same indicator and decision functions with historical bars.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, APScheduler, SQLite, Pydantic v2, httpx, yfinance, pytest, native HTML/CSS/JavaScript, GitHub Actions.

## Global Constraints

- QQQ is the only instrument that receives a suggested allocation or DCA multiplier.
- Suggested allocation states are exactly: Defensive 20%–30% / 0×, Cautious 30%–40% / 0.5×, Neutral 40% / 1×, Constructive 40%–50% / 1.5×, Opportunity 50%–60% / 2×.
- Use Wilder RSI(2) and RSI(6); do not implement or display RSI(1).
- All decision thresholds live in `config/default_rules.json`; valuation anchors never affect the state calculation.
- Dashboard refresh is best-effort and exposes source status, source timestamp, generated timestamp, and stale state. A single failed source must not blank the page.
- Do not store personal holdings, broker credentials, account IDs, or order instructions.
- The frontend is fixed dark mode with `#0A0D12` base, `#12161D` surfaces, `#232834` borders, `#E8A33D` signal emphasis, `#3DDC97` up, and `#F0656B` down.
- Numeric values use IBM Plex Mono with tabular numerals; interactive touch targets are at least 44px; motion honors `prefers-reduced-motion`.
- All output carries “仅用于个人研究参考，不构成投资建议”.

---

## File Structure

```text
app/
  config.py                 # Paths and JSON rule loading
  models.py                 # Pydantic data contracts shared by all layers
  db.py                     # SQLite schema and snapshot persistence
  providers/
    yahoo.py                # yfinance market data adapter
    cnn_fear_greed.py       # Best-effort CNN adapter
    macro_calendar.py       # FOMC/BLS calendar adapters
  services/
    indicators.py           # RSI, moving average, drawdown, volume calculations
    decision.py             # Five-state deterministic evaluation
    dashboard.py            # Payload composition and per-source fallbacks
    backtest.py             # No-lookahead strategy simulation
    export.py               # Atomic static JSON output
  scheduler.py              # Market-hours refresh job
  main.py                   # FastAPI endpoints and static asset mounting
config/
  default_rules.json        # Thresholds and exact state mapping
  valuation_anchors.json    # Editable, provenance-required background data
scripts/
  refresh_dashboard.py      # CLI: fetch, calculate, persist, export
static/
  index.html                # Single responsive dashboard page
  assets/app.css            # Terminal design system and responsive layout
  assets/app.js             # Rendering, disclosure panels, refresh highlighting
  data/dashboard.json       # Generated only; ignored locally and published as build artifact
tests/
  fixtures/                 # Deterministic bars, source responses, and calendar HTML/ICS
  test_config.py
  test_db.py
  test_providers.py
  test_indicators.py
  test_decision.py
  test_dashboard.py
  test_backtest.py
  test_export.py
  test_api.py
  test_static_assets.py
.github/workflows/
  update-dashboard.yml      # Scheduled refresh and GitHub Pages artifact deployment
requirements.txt
README.md
```

## Task 1: Bootstrap the project contracts and configuration

**Files:**
- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/models.py`
- Create: `config/default_rules.json`
- Create: `config/valuation_anchors.json`
- Create: `tests/conftest.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces `RuleConfig`, `PriceBar`, `SourceStatus`, `IndicatorSet`, `Decision`, `DashboardPayload` in `app.models`.
- Produces `load_rule_config(path: Path | None = None) -> RuleConfig` in `app.config`.
- Later tasks import these types rather than using dictionaries for domain values.

- [ ] **Step 1: Write the failing configuration test**

```python
from app.config import load_rule_config


def test_default_rules_define_all_five_states() -> None:
    rules = load_rule_config()
    assert [state.name for state in rules.states] == [
        "defensive", "cautious", "neutral", "constructive", "opportunity",
    ]
    assert rules.states[0].allocation_min == 20
    assert rules.states[-1].dca_multiplier == 2.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_config.py::test_default_rules_define_all_five_states -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'`.

- [ ] **Step 3: Implement the contracts and minimal rule loader**

```python
# app/config.py
def load_rule_config(path: Path | None = None) -> RuleConfig:
    rules_path = path or Path("config/default_rules.json")
    return RuleConfig.model_validate_json(rules_path.read_text(encoding="utf-8"))
```

```python
# app/models.py
class StateRule(BaseModel):
    name: str
    allocation_min: int
    allocation_max: int
    dca_multiplier: float


class RuleConfig(BaseModel):
    states: list[StateRule]
    thresholds: dict[str, float]


class PriceBar(BaseModel):
    day: date
    close: float
    volume: int


class SourceStatus(BaseModel):
    source: str
    available: bool
    checked_at: datetime
    stale: bool = False
    message: str | None = None


class IndicatorSet(BaseModel):
    close: float
    rsi2: float | None = None
    rsi6: float | None = None
    rsi_is_estimated: bool
    sma200: float | None = None
    drawdown_pct: float | None = None
    volume_ratio: float | None = None
    vix: float | None = None
    fear_greed: int | None = None


class Decision(BaseModel):
    state: str
    allocation_min: int
    allocation_max: int
    target_allocation: float
    dca_multiplier: float
    reasons: list[str]
    non_triggers: list[str]
    actionability: str
```

```python
# tests/conftest.py
def sample_bars(count: int = 260) -> list[PriceBar]:
    return [PriceBar(day=date(2025, 1, 1) + timedelta(days=index), close=400 + index, volume=1_000_000) for index in range(count)]


def declining_bars(count: int) -> list[PriceBar]:
    return [PriceBar(day=date(2025, 1, 1) + timedelta(days=index), close=500 - index, volume=1_000_000) for index in range(count)]
```

```json
{"states":[
  {"name":"defensive","allocation_min":20,"allocation_max":30,"dca_multiplier":0.0},
  {"name":"cautious","allocation_min":30,"allocation_max":40,"dca_multiplier":0.5},
  {"name":"neutral","allocation_min":40,"allocation_max":40,"dca_multiplier":1.0},
  {"name":"constructive","allocation_min":40,"allocation_max":50,"dca_multiplier":1.5},
  {"name":"opportunity","allocation_min":50,"allocation_max":60,"dca_multiplier":2.0}
],"thresholds":{"rsi2_oversold":15,"rsi6_oversold":30,"fear_greed_extreme":15,"vix_high":30,"drawdown_risk":12,"volume_ratio_high":2.0}}
```

- [ ] **Step 4: Add the dependency list and run the passing test**

`requirements.txt` contains `fastapi`, `uvicorn[standard]`, `apscheduler`, `httpx`, `yfinance`, `pydantic`, and `pytest` with compatible minimum versions. `tests/conftest.py` defines the shared `payload`, `rules`, `market_result`, `raising_transport`, `indicators_below_ma_with_high_vix`, `indicators_broken_trend_and_oversold`, `indicators_constructive`, and `extreme_future_bar` fixtures used by later tests.

Run: `python -m pytest tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the bootstrap contracts**

```bash
git add requirements.txt app config tests/conftest.py tests/test_config.py
git commit -m "feat: add dashboard contracts and rule configuration"
```

## Task 2: Persist market snapshots and source health in SQLite

**Files:**
- Create: `app/db.py`
- Create: `tests/test_db.py`

**Interfaces:**
- Consumes `DashboardPayload` and `SourceStatus` from `app.models`.
- Produces `SnapshotRepository(db_path: Path)`, `save_payload(payload: DashboardPayload) -> None`, `load_latest_payload() -> DashboardPayload | None`, and `record_source_status(status: SourceStatus) -> None`.
- Dashboard composition and FastAPI use `load_latest_payload()` as the cached fallback.

- [ ] **Step 1: Write the failing repository round-trip test**

```python
def test_repository_returns_latest_complete_payload(tmp_path: Path, payload: DashboardPayload) -> None:
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite3")
    repository.save_payload(payload)
    assert repository.load_latest_payload().generated_at == payload.generated_at
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_db.py::test_repository_returns_latest_complete_payload -v`

Expected: FAIL with `ImportError: cannot import name 'SnapshotRepository'`.

- [ ] **Step 3: Implement schema creation and JSON payload persistence**

```python
class SnapshotRepository:
    def save_payload(self, payload: DashboardPayload) -> None:
        serialized = payload.model_dump_json()
        self.connection.execute(
            "INSERT INTO payload_snapshots(generated_at, payload_json) VALUES (?, ?)",
            (payload.generated_at.isoformat(), serialized),
        )
        self.connection.commit()
```

Use tables `payload_snapshots(generated_at TEXT PRIMARY KEY, payload_json TEXT NOT NULL)` and `source_health(source TEXT PRIMARY KEY, checked_at TEXT NOT NULL, status_json TEXT NOT NULL)`.

- [ ] **Step 4: Add missing-payload and source-health tests**

```python
def test_empty_repository_returns_none(tmp_path: Path) -> None:
    assert SnapshotRepository(tmp_path / "empty.sqlite3").load_latest_payload() is None
```

Run: `python -m pytest tests/test_db.py -v`

Expected: PASS.

- [ ] **Step 5: Commit snapshot persistence**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat: persist dashboard snapshots and source health"
```

## Task 3: Implement source adapters with isolated fallback states

**Files:**
- Create: `app/providers/__init__.py`
- Create: `app/providers/yahoo.py`
- Create: `app/providers/cnn_fear_greed.py`
- Create: `app/providers/macro_calendar.py`
- Create: `tests/fixtures/cnn_fear_greed.json`
- Create: `tests/test_providers.py`

**Interfaces:**
- Produces `fetch_daily_bars(symbol: str, period: str) -> tuple[list[PriceBar] | None, SourceStatus]`, `fetch_quote(symbol: str) -> tuple[Quote | None, SourceStatus]`, `fetch_fear_greed(client: httpx.Client) -> tuple[FearGreedReading | None, SourceStatus]`, and `load_macro_events(client: httpx.Client, start: date, end: date) -> tuple[list[MacroEvent] | None, SourceStatus]`.
- Each adapter returns a `SourceStatus` alongside successful data, or a failed `SourceStatus` and `None`; no adapter raises network errors beyond its module boundary.

- [ ] **Step 1: Write failing fixture-backed provider tests**

```python
def test_fear_greed_maps_current_score(mock_transport: httpx.MockTransport) -> None:
    reading, status = fetch_fear_greed(httpx.Client(transport=mock_transport))
    assert reading.score == 39
    assert status.available is True


def test_fear_greed_failure_returns_unavailable_status() -> None:
    reading, status = fetch_fear_greed(httpx.Client(transport=raising_transport))
    assert reading is None
    assert status.available is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_providers.py -v`

Expected: FAIL with missing provider functions.

- [ ] **Step 3: Implement adapters with fixed timeout and exception conversion**

```python
def fetch_fear_greed(client: httpx.Client) -> tuple[FearGreedReading | None, SourceStatus]:
    try:
        response = client.get(CNN_URL, timeout=8.0)
        response.raise_for_status()
        return parse_fear_greed(response.json()), SourceStatus.available_now("cnn_fear_greed")
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        return None, SourceStatus.unavailable("cnn_fear_greed", str(error))
```

Implement the FOMC and BLS parsers against saved fixtures before enabling live requests. Use `zoneinfo.ZoneInfo("America/New_York")` to normalize displayed event times.

- [ ] **Step 4: Run provider tests and manual market fetch smoke check**

Run: `python -m pytest tests/test_providers.py -v`

Expected: PASS.

Run: `python -c "from app.providers.yahoo import fetch_daily_bars; bars, status = fetch_daily_bars('QQQ', '1y'); print(len(bars or []), status.available)"`

Expected: a positive number of QQQ daily bars or an explicit unavailable source status.

- [ ] **Step 5: Commit the adapters**

```bash
git add app/providers tests/fixtures tests/test_providers.py
git commit -m "feat: add resilient market sentiment and calendar providers"
```

## Task 4: Calculate indicators and evaluate deterministic market states

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/indicators.py`
- Create: `app/services/decision.py`
- Create: `tests/test_indicators.py`
- Create: `tests/test_decision.py`

**Interfaces:**
- Consumes `list[PriceBar]`, current quotes, optional fear/greed, and `RuleConfig`.
- Produces `calculate_indicators(bars: Sequence[PriceBar], intraday_price: float | None) -> IndicatorSet` and `evaluate_decision(indicators: IndicatorSet, rules: RuleConfig) -> Decision`.
- `Decision` includes `state`, `allocation_min`, `allocation_max`, `target_allocation`, `dca_multiplier`, `reasons`, `non_triggers`, and `actionability`. `target_allocation` is the midpoint of the state range, except Neutral is exactly 40.0.

- [ ] **Step 1: Write failing RSI and indicator tests**

```python
def test_wilder_rsi_uses_period_two_and_never_exposes_rsi_one() -> None:
    indicators = calculate_indicators(declining_bars(12), intraday_price=None)
    assert indicators.rsi2 is not None
    assert indicators.rsi6 is not None
    assert not hasattr(indicators, "rsi1")


def test_intraday_price_marks_indicator_as_estimated() -> None:
    indicators = calculate_indicators(sample_bars(), intraday_price=510.0)
    assert indicators.rsi_is_estimated is True
```

- [ ] **Step 2: Run the indicator tests to verify they fail**

Run: `python -m pytest tests/test_indicators.py -v`

Expected: FAIL with missing `calculate_indicators`.

- [ ] **Step 3: Implement pure indicator functions**

```python
def wilders_rsi(closes: Sequence[float], period: int) -> float | None:
    if period < 2 or len(closes) <= period:
        return None
    gains = [max(b - a, 0.0) for a, b in pairwise(closes)]
    losses = [max(a - b, 0.0) for a, b in pairwise(closes)]
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        average_gain = ((average_gain * (period - 1)) + gain) / period
        average_loss = ((average_loss * (period - 1)) + loss) / period
    return 100.0 if average_loss == 0 else 100 - (100 / (1 + average_gain / average_loss))
```

Compute 200-day moving average, peak-to-current drawdown, 20-day average volume ratio, and a separate `rsi_is_estimated` flag.

- [ ] **Step 4: Write the failing state-mapping tests**

```python
def test_multiple_risk_flags_map_to_defensive_state(rules: RuleConfig) -> None:
    decision = evaluate_decision(indicators_below_ma_with_high_vix(), rules)
    assert decision.state == "defensive"
    assert (decision.allocation_min, decision.allocation_max) == (20, 30)
    assert decision.dca_multiplier == 0.0


def test_oversold_only_does_not_override_broken_long_term_trend(rules: RuleConfig) -> None:
    decision = evaluate_decision(indicators_broken_trend_and_oversold(), rules)
    assert decision.state in {"defensive", "cautious"}


def test_constructive_state_lists_reasons_and_non_triggers(rules: RuleConfig) -> None:
    decision = evaluate_decision(indicators_constructive(), rules)
    assert decision.state == "constructive"
    assert decision.reasons
    assert decision.non_triggers
```

- [ ] **Step 5: Implement state precedence and run the full unit suite**

Priority order is `defensive > cautious > opportunity > constructive > neutral`. Defensive requires two long-term risk flags; Opportunity requires an oversold confirmation and no defensive condition. Every skipped optional source becomes a non-trigger entry, never a fabricated value.

Run: `python -m pytest tests/test_indicators.py tests/test_decision.py -v`

Expected: PASS.

- [ ] **Step 6: Commit the decision engine**

```bash
git add app/services/indicators.py app/services/decision.py tests/test_indicators.py tests/test_decision.py
git commit -m "feat: add transparent QQQ signal decision engine"
```

## Task 5: Compose payloads and atomically export static JSON

**Files:**
- Create: `app/services/dashboard.py`
- Create: `app/services/export.py`
- Create: `tests/test_dashboard.py`
- Create: `tests/test_export.py`

**Interfaces:**
- Consumes provider results, `IndicatorSet`, `Decision`, and the previous `DashboardPayload | None`.
- Produces `build_dashboard_payload(...) -> DashboardPayload` and `write_dashboard_json(payload: DashboardPayload, destination: Path) -> None`.
- FastAPI and the static page consume the exported `DashboardPayload` JSON unchanged.

- [ ] **Step 1: Write failing stale-fallback and export tests**

```python
def test_missing_fear_greed_keeps_market_payload_and_marks_source_unavailable() -> None:
    payload = build_dashboard_payload(market=market_result(), fear_greed=None, previous=None)
    assert payload.decision is not None
    assert payload.sources["cnn_fear_greed"].available is False


def test_export_replaces_json_atomically(tmp_path: Path, payload: DashboardPayload) -> None:
    destination = tmp_path / "dashboard.json"
    write_dashboard_json(payload, destination)
    assert DashboardPayload.model_validate_json(destination.read_text()).generated_at == payload.generated_at
    assert not list(tmp_path.glob("*.tmp"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_dashboard.py tests/test_export.py -v`

Expected: FAIL with missing composer/exporter functions.

- [ ] **Step 3: Implement payload composition and temporary-file replacement**

```python
def write_dashboard_json(payload: DashboardPayload, destination: Path) -> None:
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(destination)
```

When a live source fails and a prior payload exists, retain its last valid display value with `stale=True`; never retain a value that belongs to a different symbol.

- [ ] **Step 4: Run the payload tests**

Run: `python -m pytest tests/test_dashboard.py tests/test_export.py -v`

Expected: PASS.

- [ ] **Step 5: Commit payload export**

```bash
git add app/services/dashboard.py app/services/export.py tests/test_dashboard.py tests/test_export.py
git commit -m "feat: export resilient dashboard payloads"
```

## Task 6: Add no-lookahead backtesting and fixed-allocation comparison

**Files:**
- Create: `app/services/backtest.py`
- Create: `tests/test_backtest.py`

**Interfaces:**
- Consumes `Sequence[PriceBar]`, `RuleConfig`, and `initial_capital: float`.
- Produces `run_backtest(bars, rules, initial_capital=10_000.0) -> BacktestResult` with `daily_states`, `equity_curve`, `cumulative_return`, `max_drawdown`, `turnover`, `state_counts`, and `benchmark_return`.
- Dashboard composition reads only the summary fields; it never receives future bars.

- [ ] **Step 1: Write the failing no-lookahead test**

```python
def test_backtest_does_not_change_past_decisions_when_future_bars_change(rules: RuleConfig) -> None:
    original = run_backtest(sample_bars(260), rules)
    altered = run_backtest(sample_bars(260)[:-1] + [extreme_future_bar()], rules)
    assert original.daily_states[:-1] == altered.daily_states[:-1]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_backtest.py::test_backtest_does_not_change_past_decisions_when_future_bars_change -v`

Expected: FAIL with missing `run_backtest`.

- [ ] **Step 3: Implement daily close-only simulation**

```python
def run_backtest(bars: Sequence[PriceBar], rules: RuleConfig, initial_capital: float = 10_000.0) -> BacktestResult:
    for index in range(200, len(bars) - 1):
        indicators = calculate_indicators(bars[: index + 1], intraday_price=None)
        decision = evaluate_decision(indicators, rules)
        next_day_return = bars[index + 1].close / bars[index].close - 1
        portfolio_value *= 1 + (decision.target_allocation / 100) * next_day_return
```

The 40% benchmark uses the same next-day return and a constant `0.40` exposure. Record turnover as the absolute sum of target-allocation changes.

- [ ] **Step 4: Add drawdown, state-count, and benchmark tests**

```python
def test_backtest_reports_benchmark_and_max_drawdown(rules: RuleConfig) -> None:
    result = run_backtest(sample_bars(260), rules)
    assert result.benchmark_return is not None
    assert result.max_drawdown <= 0
    assert sum(result.state_counts.values()) == len(result.daily_states)
```

Run: `python -m pytest tests/test_backtest.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the backtest**

```bash
git add app/services/backtest.py tests/test_backtest.py
git commit -m "feat: add no-lookahead QQQ rules backtest"
```

## Task 7: Expose local API, refresh job, and command-line workflow

**Files:**
- Create: `app/scheduler.py`
- Create: `app/main.py`
- Create: `scripts/refresh_dashboard.py`
- Create: `tests/test_api.py`

**Interfaces:**
- Produces `refresh_once(repository: SnapshotRepository, export_path: Path) -> DashboardPayload`.
- Produces `GET /api/dashboard`, `GET /api/health`, and `POST /api/refresh` in `app.main`.
- `GET /api/dashboard` returns the latest persisted `DashboardPayload`, or HTTP 503 with a structured `{"detail":"No successful dashboard snapshot exists"}` body.

- [ ] **Step 1: Write failing API tests**

```python
def test_dashboard_endpoint_returns_latest_payload(client: TestClient, seeded_payload: DashboardPayload) -> None:
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    assert response.json()["decision"]["state"] == seeded_payload.decision.state


def test_dashboard_endpoint_returns_503_before_first_refresh(client: TestClient) -> None:
    response = client.get("/api/dashboard")
    assert response.status_code == 503
```

- [ ] **Step 2: Run the API tests to verify they fail**

Run: `python -m pytest tests/test_api.py -v`

Expected: FAIL with missing `app.main`.

- [ ] **Step 3: Implement refresh orchestration, endpoints, and schedule**

```python
@app.get("/api/dashboard", response_model=DashboardPayload)
def read_dashboard() -> DashboardPayload:
    payload = repository.load_latest_payload()
    if payload is None:
        raise HTTPException(status_code=503, detail="No successful dashboard snapshot exists")
    return payload
```

Schedule a 15-minute job but return without fetching when an injected `is_us_market_session(now)` check is false. The CLI invokes `refresh_once()` directly and exits non-zero only when no valid old or new payload can be exported.

- [ ] **Step 4: Run API tests and a local refresh smoke check**

Run: `python -m pytest tests/test_api.py -v`

Expected: PASS.

Run: `python scripts/refresh_dashboard.py --output static/data/dashboard.json`

Expected: a generated JSON file, or a non-zero exit with source-specific errors.

- [ ] **Step 5: Commit the local service workflow**

```bash
git add app/main.py app/scheduler.py scripts/refresh_dashboard.py tests/test_api.py
git commit -m "feat: serve and refresh dashboard locally"
```

## Task 8: Build the responsive terminal-style static dashboard

**Files:**
- Create: `static/index.html`
- Create: `static/assets/app.css`
- Create: `static/assets/app.js`
- Create: `tests/test_static_assets.py`

**Interfaces:**
- Consumes `DashboardPayload` at `data/dashboard.json` in static mode or `/api/dashboard` in FastAPI mode.
- Produces `renderDashboard(payload)`, `renderSourceDetails(payload)`, and `formatAge(timestamp)` in `static/assets/app.js`.
- `static/index.html` includes fixed container IDs: `signal-band`, `qqq-core`, `macro-grid`, `event-list`, `sector-grid`, `signal-reasons`, `backtest-summary`, and `data-status`.

- [ ] **Step 1: Write failing static-asset contract tests**

```python
def test_dashboard_markup_has_all_required_sections() -> None:
    html = Path("static/index.html").read_text(encoding="utf-8")
    for element_id in ["signal-band", "qqq-core", "macro-grid", "event-list", "sector-grid", "signal-reasons", "backtest-summary", "data-status"]:
        assert f'id="{element_id}"' in html


def test_frontend_does_not_reference_rsi_one() -> None:
    assets = Path("static/index.html").read_text(encoding="utf-8") + Path("static/assets/app.js").read_text(encoding="utf-8")
    assert "RSI(1)" not in assets
```

- [ ] **Step 2: Run the static tests to verify they fail**

Run: `python -m pytest tests/test_static_assets.py -v`

Expected: FAIL with missing static files.

- [ ] **Step 3: Implement semantic HTML and accessible rendering functions**

```javascript
function renderDashboard(payload) {
  document.querySelector("#signal-band").replaceChildren(renderSignalBand(payload.decision));
  document.querySelector("#qqq-core").replaceChildren(renderQqqCore(payload));
  document.querySelector("#data-status").replaceChildren(renderSourceDetails(payload.sources));
}
```

Use native `<details>` for source disclosure; use no decorative icon requirement; make all values `font-variant-numeric: tabular-nums`. Load Space Grotesk, IBM Plex Sans, and IBM Plex Mono. Implement single-column mobile layout first, then a dense desktop grid at 900px. Use only the approved palette and 2–4px radii.

- [ ] **Step 4: Add source loading, refresh highlighting, and reduced-motion behavior**

```javascript
async function loadDashboard() {
  const response = await fetch("data/dashboard.json", { cache: "no-store" });
  if (!response.ok) throw new Error("dashboard payload unavailable");
  renderDashboard(await response.json());
}
```

When `matchMedia("(prefers-reduced-motion: reduce)").matches` is true, omit all numeric flash and signal breathing classes.

- [ ] **Step 5: Run static tests and inspect the page at mobile and desktop widths**

Run: `python -m pytest tests/test_static_assets.py -v`

Expected: PASS.

Run: `python -m uvicorn app.main:app --reload`

Expected: local page renders without horizontal scrolling at 320px and presents the approved terminal style at desktop width.

- [ ] **Step 6: Commit the dashboard UI**

```bash
git add static tests/test_static_assets.py
git commit -m "feat: add responsive QQQ terminal dashboard"
```

## Task 9: Publish static artifacts on a market-hours schedule and document use

**Files:**
- Create: `.github/workflows/update-dashboard.yml`
- Create: `README.md`
- Modify: `.gitignore`

**Interfaces:**
- Workflow runs `python scripts/refresh_dashboard.py --output publish/data/dashboard.json` and deploys `static/` plus generated `publish/data/dashboard.json` as a GitHub Pages artifact.
- README exposes local start command, manual static export command, GitHub Pages deployment steps, source limitations, and public-site warning.

- [ ] **Step 1: Write failing workflow and README contract tests**

```python
def test_readme_discloses_data_and_investment_limitations() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "仅用于个人研究参考，不构成投资建议" in readme
    assert "yfinance" in readme
    assert "公开" in readme


def test_workflow_has_manual_and_scheduled_triggers() -> None:
    workflow = Path(".github/workflows/update-dashboard.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_static_assets.py::test_readme_discloses_data_and_investment_limitations -v`

Expected: FAIL with missing README/workflow.

- [ ] **Step 3: Implement Pages workflow and documentation**

```yaml
on:
  workflow_dispatch:
  schedule:
    - cron: "*/15 12-22 * * 1-5"
```

The refresh script itself must reject non-market sessions, so daylight-saving changes do not cause non-session snapshots. Copy `static/` to a clean `publish/` directory, write the payload under `publish/data/`, and deploy that directory as the Pages artifact. Do not commit generated live data into the repository.

README local commands:

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
python scripts/refresh_dashboard.py --output static/data/dashboard.json
python -m uvicorn app.main:app --reload
```

- [ ] **Step 4: Run tests and validate workflow syntax structurally**

Run: `python -m pytest tests/test_static_assets.py -v`

Expected: PASS.

Run: `git diff --check`

Expected: no output.

- [ ] **Step 5: Commit deployment documentation**

```bash
git add .github/workflows/update-dashboard.yml README.md .gitignore tests/test_static_assets.py
git commit -m "docs: add static dashboard deployment guide"
```

## Task 10: Run the full suite and complete the release checklist

**Files:**
- Modify: `README.md` only if a verified command differs from documentation.

**Interfaces:**
- Verifies all prior public interfaces and the static payload contract together.

- [ ] **Step 1: Execute the complete automated test suite**

Run: `python -m pytest -v`

Expected: PASS with no skipped core decision, export, backtest, API, or static-asset test.

- [ ] **Step 2: Run a local end-to-end refresh and API smoke test**

Run: `python scripts/refresh_dashboard.py --output static/data/dashboard.json`

Expected: generated payload includes `generated_at`, `sources`, `decision`, and the research disclaimer.

Run: `python -c "from fastapi.testclient import TestClient; from app.main import app; print(TestClient(app).get('/api/health').status_code)"`

Expected: `200`.

- [ ] **Step 3: Inspect the generated static payload for unsafe content**

Run: `rg -n "account|broker|password|token|持仓|成本" static/data/dashboard.json`

Expected: no output.

- [ ] **Step 4: Check the working tree and commit documentation corrections if needed**

Run: `git status --short && git diff --check`

Expected: clean working tree and no whitespace errors.

- [ ] **Step 5: Tag the verified baseline commit in the README release note**

Add a `## 验证记录` section with the exact date, test command, and successful command output summary, then run:

```bash
git add README.md
git commit -m "docs: record verified dashboard baseline"
```

## Plan Self-Review

- Spec coverage: Tasks 1–2 cover configuration and persistence; Task 3 covers sources and official calendars; Task 4 covers indicators and five-state rules; Task 5 covers degraded payloads; Task 6 covers no-lookahead backtests; Task 7 covers local FastAPI and scheduler; Task 8 covers the approved responsive terminal UI; Task 9 covers static mobile publishing and disclosures; Task 10 covers end-to-end verification.
- Placeholder scan: no `TBD`, `TODO`, “implement later”, or undefined follow-up interfaces remain.
- Type consistency: all tasks use `PriceBar`, `IndicatorSet`, `Decision`, `DashboardPayload`, `RuleConfig`, and `BacktestResult` as produced/consumed contracts; the static page consumes the `DashboardPayload` JSON emitted by Task 5.
