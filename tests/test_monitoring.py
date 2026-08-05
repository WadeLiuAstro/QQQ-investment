"""Task 2: monitoring 纯函数服务与分组/摘要契约测试。"""

from datetime import UTC, date, datetime, timedelta

from app.models import SourceStatus
from app.providers.cnn_fear_greed import (
    FearGreedFactor,
    FearGreedPoint,
    FearGreedReading,
)
from app.providers.yahoo import PriceBar
from app.services.monitoring import (
    DIRECTION_EPSILON,
    build_market_metric,
    build_monitoring,
)


def bars(closes: list[float], start: date = date(2026, 7, 15)) -> list[PriceBar]:
    return [
        PriceBar(day=start + timedelta(days=index), close=close, volume=1_000_000)
        for index, close in enumerate(closes)
    ]


def _reading() -> FearGreedReading:
    return FearGreedReading(
        score=55,
        rating="greed",
        observed_at=datetime(2026, 8, 4, tzinfo=UTC),
        previous_close=50.0,
        history=(FearGreedPoint(datetime(2026, 8, 4, tzinfo=UTC), 55.0),),
        factors=(FearGreedFactor("market_momentum", "市场动量", 60.0),),
    )


def _status(available: bool = True) -> SourceStatus:
    return SourceStatus(source="test", available=available, checked_at=datetime.now(UTC))


def _sources() -> dict[str, SourceStatus]:
    return {
        "cnn_fear_greed": _status(),
        "yahoo_qqq": _status(),
        "yahoo_vix": _status(),
        "yahoo_vix3m": _status(),
    }


def _qqq_bars() -> list[PriceBar]:
    return bars([100.0 + index * 0.5 for index in range(21)])


def monitoring_inputs(**overrides):
    qqq = _qqq_bars()
    inputs = {
        "generated_at": datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
        "bars_by_key": {
            "qqq": qqq,
            "qqqe": bars([100.0 + index * 0.4 for index in range(21)]),
            "xlk": bars([200.0 + index for index in range(21)]),
            "smh": bars([300.0 + index for index in range(21)]),
            "xle": bars([150.0 - index * 0.2 for index in range(21)]),
            "xlf": bars([90.0 + index * 0.3 for index in range(21)]),
            "vix": bars([16.0 + index * 0.1 for index in range(21)]),
            "vix3m": bars([15.0 + index * 0.05 for index in range(21)]),
            "treasury_10y": bars([4.5 + index * 0.01 for index in range(21)]),
            "dollar_index": bars([100.0 + index * 0.05 for index in range(21)]),
        },
        "market": {
            "qqq": {
                "trend": {"available": True, "regime": "bull", "deviation_pct": 6.0},
                "breadth": {
                    "available": True,
                    "label": "宽度与指数同步",
                    "relative_strength_5d": 0.9,
                    "relative_strength_20d": 0.9,
                },
                "indicators": {"moving_average_200": 105.0, "drawdown_pct": -2.0},
            }
        },
        "fear_greed": _reading(),
        "events": [],
        "sources": _sources(),
    }
    inputs.update(overrides)
    return inputs


def test_build_market_metric_exposes_latest_and_changes() -> None:
    metric = build_market_metric(
        "qqq", "QQQ", bars([100.0] * 20 + [105.0]),
        unit="USD", mode="percent", epsilon=DIRECTION_EPSILON["price_pct"],
    )
    assert metric.current == 105.0
    assert metric.change_1d == 5.0
    assert metric.momentum_20d == 5.0
    assert metric.change_unit == "%"
    assert metric.direction_5d == "rising"
    assert metric.as_of == date(2026, 8, 4)


def test_build_market_metric_points_mode() -> None:
    metric = build_market_metric(
        "vix", "VIX", bars([20.0] * 20 + [18.0]),
        unit="", mode="points", epsilon=DIRECTION_EPSILON["vol_points"],
    )
    assert metric.current == 18.0
    assert metric.change_1d == -2.0
    assert metric.change_unit == ""
    assert metric.direction_5d == "falling"


def test_build_market_metric_insufficient_history_keeps_none() -> None:
    metric = build_market_metric(
        "qqq", "QQQ", bars([100.0, 101.0]),
        unit="USD", mode="percent", epsilon=DIRECTION_EPSILON["price_pct"],
    )
    assert metric.current == 101.0
    assert metric.change_1d == 1.0
    assert metric.direction_5d is None  # < 6 bars
    assert metric.momentum_20d is None  # < 21 bars


def test_build_market_metric_missing_bars_unavailable() -> None:
    metric = build_market_metric(
        "xle", "能源板块", None,
        unit="USD", mode="percent", epsilon=DIRECTION_EPSILON["price_pct"],
    )
    assert metric.available is False
    assert metric.data_status == "unavailable"
    assert metric.current is None


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


def test_monitoring_summary_contains_no_trade_advice() -> None:
    result = build_monitoring(**monitoring_inputs())
    serialized = result.model_dump_json()
    for forbidden in ("买入", "卖出", "加仓", "减仓"):
        assert forbidden not in serialized


def test_monitoring_missing_cnn_only_degrades_sentiment() -> None:
    inputs = monitoring_inputs(fear_greed=None)
    inputs["sources"]["cnn_fear_greed"] = _status(available=False)
    result = build_monitoring(**inputs)
    assert result.groups["sentiment_volatility"].data_status in ("partial", "unavailable")
    # 其它组不受影响
    assert result.groups["sector_rotation"].data_status == "available"
    assert result.groups["core_breadth"].data_status == "available"


def test_monitoring_missing_single_sector_only_degrades_that_row() -> None:
    inputs = monitoring_inputs()
    inputs["bars_by_key"]["xlk"] = None
    result = build_monitoring(**inputs)
    sector = result.groups["sector_rotation"]
    xlk = next(m for m in sector.metrics if m.key == "xlk")
    smh = next(m for m in sector.metrics if m.key == "smh")
    assert xlk.available is False
    assert smh.available is True


def test_monitoring_stale_fallback_reuses_previous_on_failure() -> None:
    from app.services.monitoring import mark_monitoring_stale

    fresh = build_monitoring(**monitoring_inputs())
    stale = mark_monitoring_stale(fresh, datetime(2026, 8, 5, tzinfo=UTC))
    first_group = stale.groups["core_breadth"]
    assert first_group.stale is True
    metric = next(m for m in first_group.metrics if m.key == "qqq")
    assert metric.stale is True
    assert metric.as_of == date(2026, 8, 4)  # retains original date
    assert metric.data_status == "partial"


def test_monitoring_all_unavailable_still_returns_payload() -> None:
    inputs = monitoring_inputs(
        bars_by_key={key: None for key in monitoring_inputs()["bars_by_key"]},
        fear_greed=None,
    )
    result = build_monitoring(**inputs)
    assert list(result.groups) == [
        "sentiment_volatility", "core_breadth", "sector_rotation", "macro_defensive"
    ]
    for group in result.groups.values():
        assert group.data_status in ("partial", "unavailable")


# --- CNN 情绪标签五档阈值（F&G 标准）---


def _full_reading() -> FearGreedReading:
    return FearGreedReading(
        score=58,
        rating="greed",
        observed_at=datetime(2026, 8, 5, tzinfo=UTC),
        previous_close=46.0,
        previous_week=38.0,
        previous_month=33.0,
        previous_year=64.0,
    )


def test_cnn_status_five_tier_thresholds() -> None:
    from app.services.monitoring import _cnn_status

    assert _cnn_status(0) == "恐惧"
    assert _cnn_status(24) == "恐惧"
    assert _cnn_status(25) == "谨慎"
    assert _cnn_status(44) == "谨慎"
    assert _cnn_status(45) == "中性"
    assert _cnn_status(54) == "中性"
    assert _cnn_status(55) == "乐观"
    assert _cnn_status(74) == "乐观"
    assert _cnn_status(75) == "贪婪"
    assert _cnn_status(100) == "贪婪"


def test_cnn_comparisons_structured_with_auto_dates() -> None:
    inputs = monitoring_inputs(fear_greed=_full_reading())
    result = build_monitoring(**inputs)

    comps = result.groups["sentiment_volatility"].details.comparisons
    assert len(comps) == 4
    assert [c.label for c in comps] == ["上一交易日", "一周前", "一月前", "一年前"]

    first = comps[0]
    assert first.value == 46.0
    assert first.status == "中性"  # 46 ∈ [45,55)
    assert first.as_of == date(2026, 8, 4)  # observed 8/5 往前 1 天

    year = comps[3]
    assert year.value == 64.0
    assert year.status == "乐观"  # 64 ∈ [55,75)
    assert year.as_of == date(2025, 8, 5)  # 往前 365 天


def test_cnn_gauge_carries_current_score_and_label() -> None:
    inputs = monitoring_inputs(fear_greed=_full_reading())
    result = build_monitoring(**inputs)

    details = result.groups["sentiment_volatility"].details
    assert details.gauge_value == 58
    assert details.gauge_label == "乐观"
