from app.config import load_rule_config
from app.services.decision import evaluate_decision
from app.services.indicators import IndicatorSet


def indicators(**changes: float | bool | None) -> IndicatorSet:
    values: dict[str, float | bool | None] = {
        "current_price": 450.0,
        "rsi2": 50.0,
        "rsi6": 50.0,
        "moving_average_200": 400.0,
        "drawdown_pct": -2.0,
        "volume_ratio": 1.0,
        "rsi_is_estimated": False,
        "vix": 20.0,
        "fear_greed": 50.0,
    }
    values.update(changes)
    return IndicatorSet(**values)


def test_multiple_risk_flags_map_to_defensive_state() -> None:
    decision = evaluate_decision(
        indicators(current_price=350.0, drawdown_pct=-15.0, vix=35.0),
        load_rule_config(),
    )

    assert decision.state == "defensive"
    assert (decision.allocation_min, decision.allocation_max) == (20, 30)
    assert decision.dca_multiplier == 0.0
    assert "仅在强风险时考虑降低已有 QQQ 仓位" in decision.actionability


def test_oversold_does_not_override_broken_long_term_trend() -> None:
    decision = evaluate_decision(
        indicators(current_price=350.0, drawdown_pct=-15.0, rsi2=10.0, rsi6=20.0),
        load_rule_config(),
    )

    assert decision.state in {"defensive", "cautious"}


def test_constructive_state_lists_reasons_and_non_triggers() -> None:
    decision = evaluate_decision(indicators(), load_rule_config())

    assert decision.state == "constructive"
    assert decision.reasons
    assert decision.non_triggers
    assert decision.target_allocation == 45.0
