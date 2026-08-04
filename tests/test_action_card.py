from datetime import UTC, datetime

from app.config import load_rule_config
from app.models import Decision, SourceStatus
from app.services.action_card import build_action_card
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


def decision(state: str) -> Decision:
    return Decision(
        state=state,
        allocation_min=20,
        allocation_max=60,
        target_allocation=40.0,
        dca_multiplier=1.0,
        reasons=[],
        non_triggers=[],
        actionability="",
    )


def source(name: str, available: bool = True) -> SourceStatus:
    return SourceStatus(source=name, available=available, checked_at=datetime.now(UTC))


def rules():
    return load_rule_config()


def labels(card) -> set[str]:
    return {item.label for item in card.watch_conditions}


def by_label(card):
    return {item.label: item for item in card.watch_conditions}


def test_extra_top_up_ready_when_both_rsi_oversold() -> None:
    card = build_action_card(
        sample_indicators(rsi2=10.0, rsi6=20.0), decision("opportunity"), rules(), {}
    )
    assert card.extra_top_up_ready is True
    assert "超卖" in card.extra_top_up_reason


def test_extra_top_up_not_ready_when_rsi6_above_threshold() -> None:
    card = build_action_card(
        sample_indicators(rsi2=10.0, rsi6=59.57), decision("constructive"), rules(), {}
    )
    assert card.extra_top_up_ready is False
    assert "未满足" in card.extra_top_up_reason


def test_extra_top_up_not_ready_when_rsi_missing() -> None:
    card = build_action_card(
        sample_indicators(rsi2=None, rsi6=None), decision("neutral"), rules(), {}
    )
    assert card.extra_top_up_ready is False
    assert "数据不足" in card.extra_top_up_reason


def test_neutral_state_watch_conditions() -> None:
    card = build_action_card(
        sample_indicators(rsi6=55.0), decision("neutral"), rules(), {}
    )
    assert labels(card) == {"RSI(6) 站上 50", "RSI(2) 与 RSI(6) 进入超卖", "跌破 200 日均线"}
    assert by_label(card)["RSI(6) 站上 50"].condition == "RSI(6) ≥ 50"
    assert by_label(card)["RSI(6) 站上 50"].met is True
    assert by_label(card)["RSI(2) 与 RSI(6) 进入超卖"].condition == "RSI(2) ≤ 15 且 RSI(6) ≤ 30"
    assert by_label(card)["RSI(2) 与 RSI(6) 进入超卖"].met is False


def test_constructive_state_watch_conditions() -> None:
    card = build_action_card(
        sample_indicators(vix=31.0), decision("constructive"), rules(), {}
    )
    assert labels(card) == {"RSI(2) 与 RSI(6) 进入超卖", "跌破 200 日均线", "VIX 达到风险线"}
    assert by_label(card)["VIX 达到风险线"].condition == "VIX ≥ 30"
    assert by_label(card)["VIX 达到风险线"].met is True


def test_risk_state_watch_conditions() -> None:
    card = build_action_card(
        sample_indicators(drawdown_pct=-5.0, vix=20.0),
        decision("cautious"),
        rules(),
        {},
    )
    assert labels(card) == {"QQQ 重新站上 200 日均线", "回撤收窄至 -12% 以内", "VIX 回落至 30 以下"}
    assert by_label(card)["回撤收窄至 -12% 以内"].condition == "回撤 > -12%"
    assert by_label(card)["回撤收窄至 -12% 以内"].met is True


def test_opportunity_state_watch_conditions() -> None:
    card = build_action_card(
        sample_indicators(rsi6=55.0), decision("opportunity"), rules(), {}
    )
    assert labels(card) == {"RSI(6) 回升至 50 以上", "QQQ 站上 200 日均线"}
    assert by_label(card)["RSI(6) 回升至 50 以上"].met is True


def test_watch_condition_note_when_data_missing() -> None:
    card = build_action_card(
        sample_indicators(moving_average_200=None), decision("neutral"), rules(), {}
    )
    assert by_label(card)["跌破 200 日均线"].note == "暂无数据"
    assert by_label(card)["跌破 200 日均线"].met is False


def test_data_completeness_counts_and_missing_names() -> None:
    sources = {
        "yahoo_qqq": source("yahoo_qqq"),
        "yahoo_vix": source("yahoo_vix", available=False),
        "cnn_fear_greed": source("cnn_fear_greed", available=False),
        "macro_calendar": source("macro_calendar"),
        "unknown_source": source("unknown_source", available=False),
    }
    card = build_action_card(sample_indicators(), decision("neutral"), rules(), sources)

    assert card.data_completeness["available"] == 2
    assert card.data_completeness["total"] == 5
    assert card.data_completeness["missing"] == ["VIX", "恐慌贪婪指数", "unknown_source"]
