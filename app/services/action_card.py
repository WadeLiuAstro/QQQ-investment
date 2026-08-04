from app.models import ActionCard, Decision, RuleConfig, SourceStatus, WatchCondition
from app.services.indicators import IndicatorSet

# 数据源 -> 展示用中文名；未知源回退为原始键
_SOURCE_LABELS = {
    "yahoo_qqq": "QQQ 行情",
    "yahoo_xlk": "科技板块",
    "yahoo_smh": "半导体板块",
    "yahoo_xle": "能源板块",
    "yahoo_xlf": "金融板块",
    "yahoo_ixic": "纳指 K 线",
    "yahoo_vix": "VIX",
    "yahoo_vix3m": "VIX3M（约 2 周滞后）",
    "yahoo_treasury_10y": "美债收益率",
    "yahoo_dollar_index": "美元指数",
    "yahoo_quote": "实时报价",
    "cnn_fear_greed": "恐慌贪婪指数",
    "macro_calendar": "宏观日历",
}

_RISK_STATES = ("defensive", "cautious")


def build_action_card(
    indicators: IndicatorSet,
    decision: Decision,
    rules: RuleConfig,
    sources: dict[str, SourceStatus],
) -> ActionCard:
    return ActionCard(
        extra_top_up_ready=_extra_top_up_ready(indicators, rules),
        extra_top_up_reason=_extra_top_up_reason(indicators, rules),
        watch_conditions=_watch_conditions(indicators, decision.state, rules),
        data_completeness=_data_completeness(sources),
    )


def _extra_top_up_ready(indicators: IndicatorSet, rules: RuleConfig) -> bool:
    thresholds = rules.thresholds
    return (
        indicators.rsi2 is not None
        and indicators.rsi6 is not None
        and indicators.rsi2 <= thresholds["rsi2_oversold"]
        and indicators.rsi6 <= thresholds["rsi6_oversold"]
    )


def _extra_top_up_reason(indicators: IndicatorSet, rules: RuleConfig) -> str:
    thresholds = rules.thresholds
    if indicators.rsi2 is None or indicators.rsi6 is None:
        return "RSI 数据不足，无法判断"
    if _extra_top_up_ready(indicators, rules):
        return "RSI(2) 与 RSI(6) 均进入超卖区间"
    return (
        f"未满足加仓机会条件（RSI(2) ≤ {thresholds['rsi2_oversold']:g} "
        f"且 RSI(6) ≤ {thresholds['rsi6_oversold']:g}）"
    )


def _watch_conditions(
    indicators: IndicatorSet, state_name: str, rules: RuleConfig
) -> list[WatchCondition]:
    thresholds = rules.thresholds
    rsi2 = indicators.rsi2
    rsi6 = indicators.rsi6
    ma200 = indicators.moving_average_200
    price = indicators.current_price
    drawdown = indicators.drawdown_pct
    vix = indicators.vix

    rsi6_ok = rsi6 is not None
    rsi6_above_50 = rsi6_ok and rsi6 >= 50.0
    oversold = (
        rsi2 is not None
        and rsi6 is not None
        and rsi2 <= thresholds["rsi2_oversold"]
        and rsi6 <= thresholds["rsi6_oversold"]
    )
    ma200_ok = price is not None and ma200 is not None
    price_below_ma200 = ma200_ok and price < ma200
    price_above_ma200 = ma200_ok and price >= ma200
    drawdown_ok = drawdown is not None
    drawdown_cleared = drawdown_ok and drawdown > -thresholds["drawdown_risk"]
    vix_ok = vix is not None
    vix_cleared = vix_ok and vix < thresholds["vix_high"]
    vix_hit = vix_ok and vix >= thresholds["vix_high"]

    def item(label: str, condition: str, met: bool, available: bool) -> WatchCondition:
        return WatchCondition(
            label=label,
            condition=condition,
            met=met,
            note=None if available else "暂无数据",
        )

    if state_name in _RISK_STATES:
        return [
            item("QQQ 重新站上 200 日均线", "价格 ≥ 200 日均线", price_above_ma200, ma200_ok),
            item("回撤收窄至 -12% 以内", f"回撤 > {-thresholds['drawdown_risk']:g}%", drawdown_cleared, drawdown_ok),
            item("VIX 回落至 30 以下", f"VIX < {thresholds['vix_high']:g}", vix_cleared, vix_ok),
        ]
    if state_name == "neutral":
        return [
            item("RSI(6) 站上 50", "RSI(6) ≥ 50", rsi6_above_50, rsi6_ok),
            item(
                "RSI(2) 与 RSI(6) 进入超卖",
                f"RSI(2) ≤ {thresholds['rsi2_oversold']:g} 且 RSI(6) ≤ {thresholds['rsi6_oversold']:g}",
                oversold,
                rsi2 is not None and rsi6 is not None,
            ),
            item("跌破 200 日均线", "价格 < 200 日均线", price_below_ma200, ma200_ok),
        ]
    if state_name == "constructive":
        return [
            item(
                "RSI(2) 与 RSI(6) 进入超卖",
                f"RSI(2) ≤ {thresholds['rsi2_oversold']:g} 且 RSI(6) ≤ {thresholds['rsi6_oversold']:g}",
                oversold,
                rsi2 is not None and rsi6 is not None,
            ),
            item("跌破 200 日均线", "价格 < 200 日均线", price_below_ma200, ma200_ok),
            item("VIX 达到风险线", f"VIX ≥ {thresholds['vix_high']:g}", vix_hit, vix_ok),
        ]
    return [
        item("RSI(6) 回升至 50 以上", "RSI(6) ≥ 50", rsi6_above_50, rsi6_ok),
        item("QQQ 站上 200 日均线", "价格 ≥ 200 日均线", price_above_ma200, ma200_ok),
    ]


def _data_completeness(sources: dict[str, SourceStatus]) -> dict[str, object]:
    missing = [
        _SOURCE_LABELS.get(name, name)
        for name, status in sources.items()
        if not status.available
    ]
    return {
        "available": len(sources) - len(missing),
        "total": len(sources),
        "missing": missing,
    }
