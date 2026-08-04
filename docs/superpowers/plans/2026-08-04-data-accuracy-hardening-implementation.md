# P0.6 数据准确性加固 Implementation Plan

**Goal:** 修复指标数据来源审查发现的三个准确性问题：估算语义、盘中成交量低估、抓取瞬时失败。不改变任何规则阈值、决策优先级或仓位输出。

**Architecture:** 新增 `app/services/session.py` 提供美东常规交易时段判断（9:30–16:00 周一至周五，节假日暂忽略）；`fetch_quote` 用其计算 `is_intraday_estimate`；`calculate_indicators` 新增成交量外推参数；`fetch_daily_bars`/`fetch_quote` 增加 1 次重试。

## Global Constraints

- 禁止修改 `app/services/decision.py`、`config/default_rules.json` 的阈值与决策逻辑。
- 复权价（auto_adjust）改造不纳入本迭代（会改变 RSI/回撤数值，需先回测）。
- 每个 Task 严格 TDD：先写失败测试并确认失败，再最小实现，全量通过后提交；提交前 `git diff --check`。
- 任务完成后按 AGENTS.md 强制同步三份文档。

---

### Task 1: 交易时段判断与 is_intraday_estimate 修复

**Files:**
- Add: `app/services/session.py`
- Modify: `app/providers/yahoo.py`（`fetch_quote` 增加 `market_open: bool | None = None` 参数，None 时实时计算）
- Test: `tests/test_session.py`

**Interfaces:**

```python
# app/services/session.py
def is_regular_session_open(now: datetime | None = None) -> bool: ...
def session_elapsed_fraction(now: datetime | None = None) -> float | None: ...
# America/New_York；周末 False；9:30 <= t < 16:00 为盘中
# fraction = 已交易分钟 / 390，盘外返回 None
```

- [ ] Step 1: 写失败测试 `tests/test_session.py`：固定 datetime 覆盖开盘边界（9:29 关、9:30 开、15:59 开、16:00 关）、周末、fraction 边界（9:30→≈0，13:00 为 210/390）；`fetch_quote(..., market_open=False)` → `is_intraday_estimate=False`，True → True；默认路径 monkeypatch `is_regular_session_open` 验证被调用。
- [ ] Step 2: 运行确认失败（ImportError）。
- [ ] Step 3: 最小实现。
- [ ] Step 4: `pytest -q` 全量通过。
- [ ] Step 5: 提交 `feat: derive intraday estimate flag from US market session`。

---

### Task 2: 盘中成交量外推与估算标记

**Files:**
- Modify: `app/services/indicators.py`（`IndicatorSet` 增加 `volume_is_estimated: bool = False`；`calculate_indicators` 增加 `volume_elapsed_fraction: float | None = None` 参数）
- Modify: `app/scheduler.py`（盘中且最后一根 QQQ bar 为当日时传入 fraction）
- Modify: `app/services/explanation.py`（`volume_is_estimated` 时 volume 行 `note="盘中估算"`）
- Modify: `static/assets/app.js`（available 行的 note 也要显示在方向列后缀）
- Test: `tests/test_indicators.py` 追加、`tests/test_explanation.py` 追加、`tests/test_threshold_matrix_payload.py` 追加

**Rules:**
- 外推：`extrapolated = last_volume / max(fraction, 0.05)`；仅当 `market_open 且 bars[-1].day == 美东当日` 时由 scheduler 传入 fraction，其余场景不传（收盘后行为完全不变）。
- `volume_elapsed_fraction` 存在时 `volume_is_estimated=True`；volume_ratio 仍按既有 20 日均量分母计算。
- 前端：`r.note` 非空时在方向列文本后追加 `（盘中估算）`；既有"未参与本次判断"分支不变。

- [ ] Step 1: 写失败测试：
  - `test_indicators.py`：fraction=0.5、末根量 1000、前 20 日均量 1000 → volume_ratio≈2.0 且 `volume_is_estimated=True`；不传 fraction 行为不变。
  - `test_explanation.py`：`volume_is_estimated=True` → volume 行 note="盘中估算" 且 available=True。
  - `test_threshold_matrix_payload.py`：monkeypatch `is_regular_session_open=True`、`session_elapsed_fraction=0.5`，构造末根 bar 日期为当日 → payload 中 `volume_is_estimated=True`。
  - 静态契约：app.js 含 `r.note` 渲染逻辑。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 最小实现（indicators → scheduler → explanation → app.js）。
- [ ] Step 4: 全量测试通过；刷新真实快照，浏览器核验盘中/收盘标记。
- [ ] Step 5: 提交 `feat: extrapolate intraday volume ratio and mark estimates`。

---

### Task 3: Yahoo 抓取重试

**Files:**
- Modify: `app/providers/yahoo.py`（内部 `_call_with_retry`，共 2 次尝试、间隔 0.5s，sleep 可注入）
- Test: `tests/test_yahoo_provider.py` 追加

- [ ] Step 1: 写失败测试：downloader 第一次抛 ValueError、第二次成功 → 返回 bars 且调用 2 次；始终失败 → status.available=False 且恰好调用 2 次；fetch_quote 同理。
- [ ] Step 2: 运行确认失败。
- [ ] Step 3: 最小实现。
- [ ] Step 4: 全量测试通过。
- [ ] Step 5: 提交 `feat: retry yahoo fetch once on transient failure`。

---

### Task 4: 三份文档同步与最终验收

- [ ] `docs/product-roadmap.md`：P0.6 标记 ✅、交付记录与提交哈希、推荐顺序划掉。
- [ ] `CONTEXT.md`：数据流补充 session 判断与成交量外推；文件地图新增 `app/services/session.py`。
- [ ] `MEMORY.md`：记录准确性修复决策（盘中估算语义、外推口径、重试策略、复权价待回测）。
- [ ] 全量验收：`pytest -q`、`git diff --check`、`git status --short` 无快照文件。

---

## Plan Self-Review

| 需求项 | 覆盖位置 |
| --- | --- |
| 收盘后显示"收盘正式" | Task 1 |
| 盘中成交量不再系统性低估 | Task 2 外推规则 |
| 估算值必须显式标注 | Task 2 note + 前端渲染 |
| 瞬时抓取失败不立即降级 | Task 3 |
| 决策规则不变 | Global Constraints + 既有 decision 测试防回归 |
| 收盘后行为完全不变 | Task 2 仅盘中传 fraction；既有 49 测试回归 |

**已知取舍:** 节假日未排除（16:00–9:30 与周末已覆盖主要误差场景；节假日当天 Yahoo 无当日 bar，外推守卫 `bars[-1].day == 当日` 自动失效，行为回退到现状）。外推系数下限 0.05（约开盘 20 分钟内）避免极端放大。
