from typing import Sequence

from app.models import RuleConfig, ThresholdDistanceRow
from app.providers.yahoo import PriceBar
from app.services.indicators import IndicatorSet, calculate_indicators

# 固定行顺序与展示元信息：rule 键 -> (中文标签, 指标属性, 比较类型, 单位)
_RULE_META: dict[str, tuple[str, str, str, str]] = {
    "rsi2_oversold": ("RSI(2) 超卖", "rsi2", "le", "点"),
    "rsi6_oversold": ("RSI(6) 超卖", "rsi6", "le", "点"),
    "drawdown_risk": ("回撤风险", "drawdown_pct", "le", "个百分点"),
    "vix_high": ("VIX（恐慌指数）", "vix", "ge", "点"),
    "volume_ratio_high": ("异常放量", "volume_ratio", "ge", "倍"),
}

# 方向 epsilon：|最新值 - 5 个交易日前值| <= epsilon 记为平稳
_EPSILONS = {
    "rsi2_oversold": 1.0,
    "rsi6_oversold": 1.0,
    "drawdown_risk": 0.5,
    "vix_high": 0.5,
    "volume_ratio_high": 0.1,
}


def distance_to_trigger(
    current: float | None, threshold: float, kind: str
) -> float | None:
    """距离触发的有符号差值：>0 未触发，<=0 已触发。

    kind="le" 表示数值 <= 阈值触发（distance = current - threshold）；
    kind="ge" 表示数值 >= 阈值触发（distance = threshold - current）。
    """
    if current is None:
        return None
    distance = current - threshold if kind == "le" else threshold - current
    return round(distance, 2)


def five_day_direction(series: Sequence[float | None], epsilon: float) -> str | None:
    """最近 5 个交易日方向：rising / falling / flat；有效值不足 2 个返回 None。"""
    values = [value for value in series if value is not None]
    if len(values) < 2:
        return None
    delta = values[-1] - values[0]
    if delta > epsilon:
        return "rising"
    if delta < -epsilon:
        return "falling"
    return "flat"


def build_threshold_matrix(
    qqq_bars: list[PriceBar] | None,
    vix_bars: list[PriceBar] | None,
    indicators: IndicatorSet,
    rules: RuleConfig,
) -> list[ThresholdDistanceRow]:
    thresholds = rules.thresholds
    rows: list[ThresholdDistanceRow] = []
    for rule, (label, attribute, kind, unit) in _RULE_META.items():
        current = getattr(indicators, attribute)
        threshold = (
            -thresholds["drawdown_risk"]
            if rule == "drawdown_risk"
            else thresholds[rule]
        )
        condition = _condition(rule, threshold)
        distance = distance_to_trigger(current, threshold, kind)
        direction = _direction_for(rule, qqq_bars, vix_bars)
        available = current is not None
        if not available:
            note = "未参与本次判断"
        elif rule == "volume_ratio_high" and indicators.volume_is_estimated:
            note = "盘中估算"
        else:
            note = None
        rows.append(
            ThresholdDistanceRow(
                rule=rule,
                label=label,
                current=current,
                condition=condition,
                distance=distance,
                unit=unit,
                direction=direction,
                available=available,
                note=note,
            )
        )
    return rows


def _condition(rule: str, threshold: float) -> str:
    number = f"{threshold:g}"
    if rule == "drawdown_risk":
        return f"≤ {number}%"
    return f"{'≤' if rule.startswith('rsi') or rule == 'drawdown_risk' else '≥'} {number}{' 倍' if rule == 'volume_ratio_high' else ''}"


def _direction_for(
    rule: str, qqq_bars: list[PriceBar] | None, vix_bars: list[PriceBar] | None
) -> str | None:
    epsilon = _EPSILONS[rule]
    if rule == "vix_high":
        if not vix_bars:
            return None
        return five_day_direction([bar.close for bar in vix_bars[-5:]], epsilon)
    if not qqq_bars:
        return None
    direction = five_day_direction(_indicator_series(qqq_bars, rule), epsilon)
    if rule == "drawdown_risk":
        return {"rising": "narrowing", "falling": "widening"}.get(direction, direction)
    return direction


def _indicator_series(bars: list[PriceBar], rule: str) -> list[float | None]:
    """按时间旧->新，重算最近 5 个交易日的指标值序列（不含盘中估算）。"""
    attribute = _RULE_META[rule][1]
    series: list[float | None] = []
    for index in (4, 3, 2, 1, 0):
        subset = bars if index == 0 else bars[:-index]
        series.append(getattr(calculate_indicators(subset), attribute))
    return series
