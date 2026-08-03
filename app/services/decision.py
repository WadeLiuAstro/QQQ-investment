from app.models import Decision, RuleConfig, StateRule
from app.services.indicators import IndicatorSet


ACTIONABILITY = {
    "defensive": "暂停后续定投；仅在强风险时考虑降低已有 QQQ 仓位。",
    "cautious": "减少后续定投；普通偏空信号不建议卖出现有 QQQ。",
    "neutral": "按既定计划定投，维持目标仓位附近。",
    "constructive": "可按规则提高本期定投金额，仍受仓位上限约束。",
    "opportunity": "可提高本期定投金额，维持仓位上限且不追涨。",
}


def evaluate_decision(indicators: IndicatorSet, rules: RuleConfig) -> Decision:
    risk_flags = _risk_flags(indicators, rules)
    if len(risk_flags) >= 2:
        state_name = "defensive"
        reasons = risk_flags
    elif risk_flags:
        state_name = "cautious"
        reasons = risk_flags
    elif _is_oversold(indicators, rules):
        state_name = "opportunity"
        reasons = ["RSI(2) 与 RSI(6) 同时处于超卖区间"]
    elif _is_constructive(indicators):
        state_name = "constructive"
        reasons = ["QQQ 位于 200 日均线之上，短中期动量未转弱"]
    else:
        state_name = "neutral"
        reasons = ["未触发风险或超卖条件，维持常规定投节奏"]

    state = _state(rules, state_name)
    return Decision(
        state=state.name,
        allocation_min=state.allocation_min,
        allocation_max=state.allocation_max,
        target_allocation=_target_allocation(state),
        dca_multiplier=state.dca_multiplier,
        reasons=reasons,
        non_triggers=_non_triggers(indicators, rules, state_name),
        actionability=ACTIONABILITY[state_name],
    )


def _risk_flags(indicators: IndicatorSet, rules: RuleConfig) -> list[str]:
    flags: list[str] = []
    thresholds = rules.thresholds
    if (
        indicators.current_price is not None
        and indicators.moving_average_200 is not None
        and indicators.current_price < indicators.moving_average_200
    ):
        flags.append("QQQ 跌破 200 日均线")
    if (
        indicators.drawdown_pct is not None
        and indicators.drawdown_pct <= -thresholds["drawdown_risk"]
    ):
        flags.append(f"回撤达到 {abs(indicators.drawdown_pct):.2f}%")
    if indicators.vix is not None and indicators.vix >= thresholds["vix_high"]:
        flags.append(f"VIX 升至 {indicators.vix:.2f}")
    return flags


def _is_oversold(indicators: IndicatorSet, rules: RuleConfig) -> bool:
    thresholds = rules.thresholds
    return (
        indicators.rsi2 is not None
        and indicators.rsi6 is not None
        and indicators.rsi2 <= thresholds["rsi2_oversold"]
        and indicators.rsi6 <= thresholds["rsi6_oversold"]
    )


def _is_constructive(indicators: IndicatorSet) -> bool:
    return (
        indicators.current_price is not None
        and indicators.moving_average_200 is not None
        and indicators.current_price >= indicators.moving_average_200
        and indicators.rsi6 is not None
        and indicators.rsi6 >= 50.0
    )


def _non_triggers(
    indicators: IndicatorSet, rules: RuleConfig, state_name: str
) -> list[str]:
    non_triggers = [f"未触发更高优先级状态：{state_name}"]
    if indicators.fear_greed is None:
        non_triggers.append("恐贪指数不可用，未纳入本次判断")
    elif indicators.fear_greed > rules.thresholds["fear_greed_extreme"]:
        non_triggers.append("恐贪指数未达到极端恐惧阈值")
    if indicators.volume_ratio is None:
        non_triggers.append("成交量数据不足，未纳入异常成交量确认")
    elif indicators.volume_ratio < rules.thresholds["volume_ratio_high"]:
        non_triggers.append("未触发异常成交量确认")
    return non_triggers


def _state(rules: RuleConfig, name: str) -> StateRule:
    return next(state for state in rules.states if state.name == name)


def _target_allocation(state: StateRule) -> float:
    if state.name == "neutral":
        return 40.0
    return (state.allocation_min + state.allocation_max) / 2
