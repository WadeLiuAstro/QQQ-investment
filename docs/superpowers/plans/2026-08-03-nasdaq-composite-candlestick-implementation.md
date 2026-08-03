# 纳斯达克综合指数 K 线卡片 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在信号带下方提供可交互、移动端自适应的 `^IXIC` 日 K 图和当日涨跌展示，但不影响 QQQ 决策。

**Architecture:** yfinance 日线适配器扩展为携带可选 OHLC 字段，刷新服务把近一年 `^IXIC` 蜡烛数据和独立来源状态导出到 `market.ixic`。静态页面以固定版本 Lightweight Charts 渲染预加载数据并在浏览器本地切换时间范围；卡片数据缺失时独立降级。

**Tech Stack:** Python 3.11、yfinance、FastAPI/静态 JSON、Lightweight Charts 4.2.3 CDN、原生 JavaScript/CSS、pytest。

## Global Constraints

- `^IXIC` 仅展示，不得输入 QQQ 决策、仓位规则或回测。
- 仅使用日 K，最长导出一年；默认展示三个月。
- 上涨色固定为 `#3DDC97`，下跌色固定为 `#F0656B`。
- 图表切换在浏览器本地筛选，不能触发新的数据源请求。
- 来源失败只降级该卡片；首次失败显示“数据暂不可用”。
- 所有新行为先写失败测试，再写最小实现。

---

### Task 1: 扩展 Yahoo 日线与指数载荷

**Files:** Modify `app/providers/yahoo.py`, `app/scheduler.py`; create `tests/test_yahoo_ohlc.py`, `tests/test_ixic_payload.py`.

**Interfaces:** `PriceBar(day, close, volume, open=None, high=None, low=None)`；`market["ixic"]` 含 `candles: list[dict[str, float | str]]`、`daily_change_points`、`daily_change_pct`。

- [ ] **Step 1: 写入失败的 OHLC 映射测试**

```python
def test_yahoo_daily_bars_include_ohlc_when_response_provides_it() -> None:
    frame = pd.DataFrame([[100.0, 105.0, 98.0, 102.0, 1_000]], columns=["Open", "High", "Low", "Close", "Volume"], index=pd.to_datetime(["2026-08-03"]))
    bars, status = fetch_daily_bars("^IXIC", "1y", downloader=lambda *_a, **_k: frame)
    assert status.available is True
    assert (bars[0].open, bars[0].high, bars[0].low, bars[0].close) == (100.0, 105.0, 98.0, 102.0)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_yahoo_ohlc.py -v -p no:cacheprovider`
Expected: FAIL，因为 `PriceBar` 尚未提供 OHLC 字段。

- [ ] **Step 3: 实现最小 OHLC 与 `^IXIC` 载荷**

```python
@dataclass(frozen=True)
class PriceBar:
    day: date
    close: float
    volume: int
    open: float | None = None
    high: float | None = None
    low: float | None = None

SYMBOLS["ixic"] = "^IXIC"

def _candles(bars: Sequence[PriceBar]) -> list[dict[str, float | str]]:
    return [{"time": bar.day.isoformat(), "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close} for bar in bars if None not in (bar.open, bar.high, bar.low)]
```

`_market_card` 对 `^IXIC` 追加 `candles` 与 `daily_change_points`；其他标的不输出蜡烛数组。

- [ ] **Step 4: 写入、运行载荷测试并提交**

```python
def test_ixic_market_card_exports_candles_and_daily_change() -> None:
    card = _market_card("^IXIC", sample_ohlc_bars())
    assert card["daily_change_points"] == 2.0
    assert card["candles"][0]["time"] == "2026-08-03"
```

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_yahoo_ohlc.py tests\test_ixic_payload.py -v -p no:cacheprovider`
Expected: PASS.

```powershell
git add app/providers/yahoo.py app/scheduler.py tests/test_yahoo_ohlc.py tests/test_ixic_payload.py
git commit -m "feat: export Nasdaq composite OHLC data"
```

### Task 2: 创建可交互的纳斯达克综合指数 K 线卡片

**Files:** Modify `static/index.html`, `static/assets/style.css`, `static/assets/app.js`; create `tests/test_ixic_static.py`.

**Interfaces:** Consumes `DashboardPayload.market.ixic`; produces `renderNasdaqComposite(ixic)`, `filterCandles(candles, range)` 和 `#nasdaq-composite` 卡片。

- [ ] **Step 1: 写入失败的静态结构测试**

```python
def test_static_page_has_nasdaq_composite_chart_contract() -> None:
    html = Path("static/index.html").read_text(encoding="utf-8")
    script = Path("static/assets/app.js").read_text(encoding="utf-8")
    assert 'id="nasdaq-composite"' in html
    assert 'id="ixic-chart"' in html
    assert 'data-range="3m"' in html
    assert "renderNasdaqComposite" in script
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_ixic_static.py -v -p no:cacheprovider`
Expected: FAIL，因为卡片及渲染函数不存在。

- [ ] **Step 3: 添加页面、样式与图表库**

在信号带后加入全宽卡片，包括 `^IXIC` 中文标题、点位、点数/百分比、`1m/3m/6m/1y` 按钮、`#ixic-chart`、`#ixic-ohlc` 和不可用提示。固定引入：

```html
<script src="https://unpkg.com/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"></script>
```

使用 `#3DDC97`、`#F0656B` 定义蜡烛实体、边框和影线；高度桌面 360px、移动端 280px，按钮在窄屏换行。

- [ ] **Step 4: 实现本地周期筛选、图表与 OHLC 提示**

```javascript
function filterCandles(candles, range) {
  const days = {"1m": 31, "3m": 92, "6m": 184, "1y": 366}[range];
  const cutoff = new Date(candles.at(-1).time);
  cutoff.setDate(cutoff.getDate() - days);
  return candles.filter(candle => new Date(candle.time) >= cutoff);
}
```

`renderNasdaqComposite` 创建或更新单例图表，默认 `3m`；十字线移动更新 OHLC；`ResizeObserver` 更新宽度；空蜡烛数组显示“数据暂不可用”。

- [ ] **Step 5: 运行静态测试并提交**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_ixic_static.py tests\test_static.py -v -p no:cacheprovider`
Expected: PASS.

```powershell
git add static/index.html static/assets/style.css static/assets/app.js tests/test_ixic_static.py
git commit -m "feat: render Nasdaq composite candlestick card"
```

### Task 3: 验证独立降级、刷新和发布产物

**Files:** Modify `app/services/dashboard.py`, `tests/test_dashboard.py`, `README.md`.

**Interfaces:** Consumes `yahoo_ixic` 不可用状态、上一份 `DashboardPayload.market.ixic`；produces `stale=True` 的独立来源状态和可继续渲染的历史蜡烛数组。

- [ ] **Step 1: 写入失败的独立降级测试**

```python
def test_missing_ixic_reuses_only_prior_ixic_card_and_marks_it_stale() -> None:
    payload = build_dashboard_payload(generated_at=timestamp, sources={"yahoo_ixic": unavailable_status}, market={"qqq": current_qqq_card}, previous=previous_with_ixic)
    assert payload.market["ixic"]["candles"] == previous_with_ixic.market["ixic"]["candles"]
    assert payload.sources["yahoo_ixic"].stale is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_dashboard.py -v -p no:cacheprovider`
Expected: FAIL，因为现有回退只处理整个市场字典而非单标的。

- [ ] **Step 3: 实现同标的回退并更新说明**

`build_dashboard_payload` 对不可用的 `yahoo_ixic` 仅从 `previous.market["ixic"]` 回填指数卡片，保留本轮可用 QQQ/板块数据；README 明确指数卡片为市场背景、非交易信号。

- [ ] **Step 4: 全量验证、真实刷新并提交/推送**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m scripts.refresh_dashboard
Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -UseBasicParsing
git diff --check
git add app/services/dashboard.py tests/test_dashboard.py README.md
git commit -m "feat: degrade Nasdaq composite chart independently"
git push origin qqq-dashboard
git push origin HEAD:main
```

Expected: 测试通过；刷新产物含 `market.ixic.candles`；主页返回 HTTP 200。

## Plan Self-Review

- Spec coverage: Task 1 覆盖日线 OHLC、`^IXIC`、来源状态；Task 2 覆盖位置、周期、配色、交互和移动端；Task 3 覆盖独立失败降级、刷新和发布。
- Placeholder scan: 未包含 TBD、TODO 或未定义实现步骤。
- Type consistency: `PriceBar` 是 OHLC 唯一来源；`market.ixic.candles` 是卡片输入；`yahoo_ixic` 是降级状态键。