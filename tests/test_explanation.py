from datetime import date, timedelta

from app.config import load_rule_config
from app.models import RuleConfig
from app.providers.yahoo import PriceBar
from app.services.explanation import (
    build_threshold_matrix,
    distance_to_trigger,
    five_day_direction,
)
from app.services.indicators import IndicatorSet


def sample_indicators(**overrides) -> IndicatorSet:
    defaults = {
        "current_price": 500.0,
        "rsi2": 75.88,
        "rsi6": 49.41,
        "moving_average_200": 490.0,
        "drawdown_pct": -7.8,
        "volume_ratio": 1.26,
        "rsi_is_estimated": False,
        "vix": 16.01,
        "fear_greed": 50.0,
    }
    defaults.update(overrides)
    return IndicatorSet(**defaults)


def bars_from_closes(closes: list[float], volumes: list[int] | None = None) -> list[PriceBar]:
    start = date(2025, 1, 1)
    return [
        PriceBar(
            day=start + timedelta(days=index),
            close=close,
            volume=(volumes or [1_000_000] * len(closes))[index],
        )
        for index, close in enumerate(closes)
    ]


def by_rule(rows):
    return {row.rule: row for row in rows}


def test_distances_match_spec_examples() -> None:
    rows = build_threshold_matrix(None, None, sample_indicators(), load_rule_config())
    matrix = by_rule(rows)

    assert matrix["rsi2_oversold"].distance == 60.88
    assert matrix["rsi6_oversold"].distance == 19.41
    assert matrix["drawdown_risk"].distance == 4.2
    assert matrix["vix_high"].distance == 13.99
    assert matrix["volume_ratio_high"].distance == 0.74
    assert [row.rule for row in rows] == [
        "rsi2_oversold",
        "rsi6_oversold",
        "drawdown_risk",
        "vix_high",
        "volume_ratio_high",
    ]
    assert matrix["vix_high"].label == "VIX（恐慌指数）"


def test_triggered_rule_has_non_positive_distance() -> None:
    rows = build_threshold_matrix(
        None, None, sample_indicators(rsi2=10.0), load_rule_config()
    )
    row = by_rule(rows)["rsi2_oversold"]

    assert row.distance == -5.0
    assert row.current == 10.0


def test_direction_uses_five_trading_day_delta_with_epsilon() -> None:
    assert five_day_direction([10, 11, 12, 13, 14], 1.0) == "rising"
    assert five_day_direction([14, 13, 12, 11, 10], 1.0) == "falling"
    assert five_day_direction([10, 10, 11, 10, 10.5], 1.0) == "flat"
    assert five_day_direction([None, 10], 1.0) is None


def test_drawdown_direction_labels_are_widening_or_narrowing() -> None:
    widening_bars = bars_from_closes(
        [100.0] * 24 + [120.0, 115.0, 110.0, 105.0, 100.0, 95.0]
    )
    narrowing_bars = bars_from_closes(
        [100.0] * 24 + [120.0, 95.0, 100.0, 105.0, 110.0, 115.0]
    )

    widening_row = by_rule(
        build_threshold_matrix(
            widening_bars, None, sample_indicators(drawdown_pct=-20.83), load_rule_config()
        )
    )["drawdown_risk"]
    narrowing_row = by_rule(
        build_threshold_matrix(
            narrowing_bars, None, sample_indicators(drawdown_pct=-4.17), load_rule_config()
        )
    )["drawdown_risk"]

    assert widening_row.direction == "widening"
    assert narrowing_row.direction == "narrowing"


def test_vix_direction_uses_recent_closes() -> None:
    vix_bars = bars_from_closes([16.0] * 25 + [12.0, 14.0, 16.0, 18.0, 20.0])
    row = by_rule(
        build_threshold_matrix(None, vix_bars, sample_indicators(vix=20.0), load_rule_config())
    )["vix_high"]

    assert row.direction == "rising"


def test_qqt_rule_directions_come_from_recomputed_series() -> None:
    closes = [100.0 + index for index in range(30)]
    row = by_rule(
        build_threshold_matrix(
            bars_from_closes(closes),
            None,
            sample_indicators(rsi2=100.0, rsi6=100.0, drawdown_pct=0.0, volume_ratio=1.0),
            load_rule_config(),
        )
    )

    assert row["rsi2_oversold"].direction == "flat"
    assert row["volume_ratio_high"].direction == "flat"


def test_missing_indicator_marks_row_unavailable() -> None:
    row = by_rule(
        build_threshold_matrix(None, None, sample_indicators(vix=None), load_rule_config())
    )["vix_high"]

    assert row.available is False
    assert row.current is None
    assert row.distance is None
    assert row.direction is None
    assert row.note == "未参与本次判断"


def test_estimated_volume_row_is_marked_but_stays_available() -> None:
    row = by_rule(
        build_threshold_matrix(
            None, None, sample_indicators(volume_is_estimated=True), load_rule_config()
        )
    )["volume_ratio_high"]

    assert row.available is True
    assert row.note == "盘中估算"
    assert row.distance == 0.74


def test_matrix_reads_thresholds_from_rules_not_hardcoded() -> None:
    rules = RuleConfig(
        states=[],
        thresholds={
            "rsi2_oversold": 20.0,
            "rsi6_oversold": 30.0,
            "vix_high": 25.0,
            "drawdown_risk": 10.0,
            "volume_ratio_high": 1.5,
        },
    )
    matrix = by_rule(build_threshold_matrix(None, None, sample_indicators(), rules))

    assert matrix["rsi2_oversold"].distance == round(75.88 - 20.0, 2)
    assert matrix["vix_high"].distance == round(25.0 - 16.01, 2)
    assert matrix["drawdown_risk"].distance == round(-7.8 + 10.0, 2)
    assert matrix["volume_ratio_high"].distance == round(1.5 - 1.26, 2)


def test_distance_to_trigger_sign_convention() -> None:
    assert distance_to_trigger(75.88, 15.0, "le") == 60.88
    assert distance_to_trigger(10.0, 15.0, "le") == -5.0
    assert distance_to_trigger(16.01, 30.0, "ge") == 13.99
    assert distance_to_trigger(35.0, 30.0, "ge") == -5.0
    assert distance_to_trigger(None, 15.0, "le") is None
