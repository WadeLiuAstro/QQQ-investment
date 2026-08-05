"""Task 2: 监控指标增强区纯函数服务（监控佐证层）。

职责：统一"最新值 + 1 日变化 + 5 日方向 + 20 日趋势"口径，组装四张摘要卡与
四个固定分组。本层只输出事实性描述与数据状态，绝不产生买入/卖出/加仓/减仓
建议，也不参与正式五档决策。
"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Literal

from app.models import (
    MacroEvent,
    MonitoringComparison,
    MonitoringDetails,
    MonitoringFactor,
    MonitoringGroup,
    MonitoringMetric,
    MonitoringPayload,
    MonitoringPoint,
    MonitoringSummary,
    SourceStatus,
)
from app.providers.cnn_fear_greed import FearGreedReading
from app.providers.yahoo import PriceBar

DIRECTION_EPSILON = {
    "price_pct": 0.5,
    "cnn_points": 1.0,
    "vol_points": 0.5,
    "macro_points": 0.1,
}

_GROUP_ORDER = [
    ("sentiment_volatility", "情绪与波动"),
    ("core_breadth", "核心趋势与宽度"),
    ("sector_rotation", "板块轮动"),
    ("macro_defensive", "宏观与防御背景"),
]

_SECTOR_ASSETS = [
    ("xlk", "科技板块（XLK）"),
    ("smh", "半导体板块（SMH）"),
    ("xle", "能源板块（XLE）"),
    ("xlf", "金融板块（XLF）"),
]


def build_monitoring(
    *,
    generated_at: datetime,
    bars_by_key: Mapping[str, Sequence[PriceBar] | None],
    market: Mapping[str, dict[str, object]],
    fear_greed: FearGreedReading | None,
    events: Sequence[MacroEvent],
    sources: Mapping[str, SourceStatus],
    previous: MonitoringPayload | None = None,
) -> MonitoringPayload:
    bars_by_key = dict(bars_by_key or {})
    market = market or {}

    builders = {
        "sentiment_volatility": lambda: _build_sentiment_group(bars_by_key, fear_greed),
        "core_breadth": lambda: _build_core_breadth_group(bars_by_key, market),
        "sector_rotation": lambda: _build_sector_group(bars_by_key),
        "macro_defensive": lambda: _build_macro_group(bars_by_key, events),
    }

    groups: dict[str, MonitoringGroup] = {}
    for key, label in _GROUP_ORDER:
        try:
            groups[key] = builders[key]()
        except Exception:  # 单组失败只降级该组，不影响其它组与正式决策
            groups[key] = MonitoringGroup(
                key=key,
                label=label,
                status="不可用",
                data_status="unavailable",
                available=False,
            )

    summary = _build_summary(groups, market)
    return MonitoringPayload(generated_at=generated_at, summary=summary, groups=groups)


def mark_monitoring_stale(
    previous: MonitoringPayload, generated_at: datetime
) -> MonitoringPayload:
    """整个 monitoring 构建失败时，复用上一快照并整体标记过期。"""
    groups: dict[str, MonitoringGroup] = {}
    for key, group in previous.groups.items():
        metrics = [
            metric.model_copy(
                update={
                    "stale": True,
                    "data_status": _downgrade(metric.data_status),
                }
            )
            for metric in group.metrics
        ]
        groups[key] = group.model_copy(
            update={
                "stale": True,
                "metrics": metrics,
                "data_status": _downgrade(group.data_status),
            }
        )
    summary = [
        card.model_copy(
            update={"stale": True, "data_status": _downgrade(card.data_status)}
        )
        for card in previous.summary
    ]
    return MonitoringPayload(generated_at=generated_at, summary=summary, groups=groups)


def build_market_metric(
    key: str,
    label: str,
    bars: Sequence[PriceBar] | None,
    *,
    unit: str,
    mode: Literal["percent", "points"],
    epsilon: float,
) -> MonitoringMetric:
    if not bars:
        return MonitoringMetric(
            key=key,
            label=label,
            available=False,
            tone="unavailable",
            display_status="不可用",
            data_status="unavailable",
        )
    current = bars[-1].close
    change_1d = _change(current, bars[-2].close, mode) if len(bars) >= 2 else None
    change_5d = _change(current, bars[-6].close, mode) if len(bars) >= 6 else None
    momentum_20d = _change(current, bars[-21].close, mode) if len(bars) >= 21 else None
    change_unit = "%" if mode == "percent" else unit
    return MonitoringMetric(
        key=key,
        label=label,
        current=current,
        unit=unit,
        change_1d=change_1d,
        change_unit=change_unit,
        direction_5d=_direction(change_5d, epsilon),
        momentum_20d=momentum_20d,
        momentum_unit=change_unit,
        as_of=bars[-1].day,
        tone=_asset_tone(change_1d),
    )


# ---------------------------------------------------------------------------
# 分组构建
# ---------------------------------------------------------------------------


def _build_sentiment_group(
    bars_by_key: Mapping[str, Sequence[PriceBar] | None],
    fear_greed: FearGreedReading | None,
) -> MonitoringGroup:
    metrics: list[MonitoringMetric] = []
    if fear_greed is not None:
        metrics.append(
            MonitoringMetric(
                key="cnn_score",
                label="CNN 市场情绪",
                current=float(fear_greed.score),
                unit="",
                as_of=fear_greed.observed_at.date(),
                tone=_cnn_tone(fear_greed.score),
                display_status=_cnn_status(fear_greed.score),
            )
        )
    else:
        metrics.append(_unavailable_metric("cnn_score", "CNN 市场情绪"))

    for asset_key, asset_label in (("vix", "VIX"), ("vix3m", "VIX3M")):
        metric = build_market_metric(
            asset_key,
            asset_label,
            bars_by_key.get(asset_key),
            unit="",
            mode="points",
            epsilon=DIRECTION_EPSILON["vol_points"],
        )
        if metric.available:
            metric = metric.model_copy(update={"tone": _risk_tone(metric.change_1d)})
        metrics.append(metric)

    details = _sentiment_details(fear_greed, bars_by_key)
    data_status = _group_data_status(metrics)
    return MonitoringGroup(
        key="sentiment_volatility",
        label="情绪与波动",
        status=_group_status_label(data_status),
        data_status=data_status,
        available=data_status != "unavailable",
        metrics=metrics,
        details=details,
    )


def _build_core_breadth_group(
    bars_by_key: Mapping[str, Sequence[PriceBar] | None],
    market: Mapping[str, dict[str, object]],
) -> MonitoringGroup:
    qqq_card = market.get("qqq") or {}
    trend = (qqq_card.get("trend") or {}) if isinstance(qqq_card, dict) else {}
    breadth = (qqq_card.get("breadth") or {}) if isinstance(qqq_card, dict) else {}
    indicators = (qqq_card.get("indicators") or {}) if isinstance(qqq_card, dict) else {}

    metrics: list[MonitoringMetric] = [
        build_market_metric(
            "qqq", "QQQ", bars_by_key.get("qqq"),
            unit="USD", mode="percent", epsilon=DIRECTION_EPSILON["price_pct"],
        ),
        build_market_metric(
            "qqqe", "QQQE", bars_by_key.get("qqqe"),
            unit="USD", mode="percent", epsilon=DIRECTION_EPSILON["price_pct"],
        ),
        _scalar_metric(
            "ma200", "200 日均线", indicators.get("moving_average_200"), unit="USD"
        ),
        _scalar_metric(
            "drawdown",
            "回撤",
            indicators.get("drawdown_pct"),
            unit="%",
            tone="negative"
            if isinstance(indicators.get("drawdown_pct"), (int, float))
            and indicators.get("drawdown_pct") <= -8
            else "neutral",
        ),
        _scalar_metric(
            "breadth_rs_5d", "宽度 RS 5 日", breadth.get("relative_strength_5d"), unit="百分点"
        ),
        _scalar_metric(
            "breadth_rs_20d", "宽度 RS 20 日", breadth.get("relative_strength_20d"), unit="百分点"
        ),
    ]

    data_status = _group_data_status(metrics)
    regime = trend.get("regime") if isinstance(trend, dict) else None
    if regime == "bull":
        status = "多头环境"
    elif regime == "bear":
        status = "空头环境"
    else:
        status = _group_status_label(data_status)

    return MonitoringGroup(
        key="core_breadth",
        label="核心趋势与宽度",
        status=status,
        data_status=data_status,
        available=data_status != "unavailable",
        metrics=metrics,
    )


def _build_sector_group(
    bars_by_key: Mapping[str, Sequence[PriceBar] | None],
) -> MonitoringGroup:
    metrics = [
        build_market_metric(
            key, label, bars_by_key.get(key),
            unit="USD", mode="percent", epsilon=DIRECTION_EPSILON["price_pct"],
        )
        for key, label in _SECTOR_ASSETS
    ]
    data_status = _group_data_status(metrics)
    return MonitoringGroup(
        key="sector_rotation",
        label="板块轮动",
        status=_group_status_label(data_status),
        data_status=data_status,
        available=data_status != "unavailable",
        metrics=metrics,
    )


def _build_macro_group(
    bars_by_key: Mapping[str, Sequence[PriceBar] | None],
    events: Sequence[MacroEvent],
) -> MonitoringGroup:
    metrics = [
        build_market_metric(
            "treasury_10y", "10 年美债收益率", bars_by_key.get("treasury_10y"),
            unit="%", mode="points", epsilon=DIRECTION_EPSILON["macro_points"],
        ),
        build_market_metric(
            "dollar_index", "美元指数", bars_by_key.get("dollar_index"),
            unit="", mode="points", epsilon=DIRECTION_EPSILON["macro_points"],
        ),
    ]
    data_status = _group_data_status(metrics)
    return MonitoringGroup(
        key="macro_defensive",
        label="宏观与防御背景",
        status=_group_status_label(data_status),
        data_status=data_status,
        available=data_status != "unavailable",
        metrics=metrics,
        details=MonitoringDetails(events=list(events or [])),
    )


# ---------------------------------------------------------------------------
# 摘要
# ---------------------------------------------------------------------------


def _build_summary(
    groups: Mapping[str, MonitoringGroup],
    market: Mapping[str, dict[str, object]],
) -> list[MonitoringSummary]:
    qqq_card = market.get("qqq") or {}
    trend = (qqq_card.get("trend") or {}) if isinstance(qqq_card, dict) else {}
    breadth = (qqq_card.get("breadth") or {}) if isinstance(qqq_card, dict) else {}
    sentiment_group = groups["sentiment_volatility"]
    core_group = groups["core_breadth"]

    summary: list[MonitoringSummary] = []

    cnn = _find_metric(sentiment_group, "cnn_score")
    if cnn is not None and cnn.available and cnn.current is not None:
        summary.append(
            MonitoringSummary(
                key="sentiment",
                label="CNN 市场情绪",
                display_value=_fmt(cnn.current),
                status=_cnn_status(cnn.current),
                tone=_cnn_tone(cnn.current),
                as_of=cnn.as_of,
            )
        )
    else:
        summary.append(_unavailable_summary("sentiment", "CNN 市场情绪"))

    regime = trend.get("regime") if isinstance(trend, dict) else None
    if regime in ("bull", "bear"):
        regime_label = "多头环境" if regime == "bull" else "空头环境"
        summary.append(
            MonitoringSummary(
                key="core_trend",
                label="QQQ 核心趋势",
                display_value=regime_label,
                status=regime_label,
                tone="positive" if regime == "bull" else "negative",
                data_status=core_group.data_status,
                available=core_group.available,
            )
        )
    else:
        summary.append(_unavailable_summary("core_trend", "QQQ 核心趋势"))

    breadth_label = breadth.get("label") if isinstance(breadth, dict) else None
    if breadth_label:
        summary.append(
            MonitoringSummary(
                key="breadth",
                label="市场宽度",
                display_value=str(breadth_label),
                status=str(breadth_label),
                tone="neutral",
                data_status=core_group.data_status,
                available=core_group.available,
            )
        )
    else:
        summary.append(_unavailable_summary("breadth", "市场宽度"))

    vix = _find_metric(sentiment_group, "vix")
    if vix is not None and vix.available and vix.current is not None:
        summary.append(
            MonitoringSummary(
                key="volatility",
                label="波动率体制",
                display_value=f"VIX {_fmt(vix.current)}",
                status=sentiment_group.details.term_status
                or ("波动升温" if (vix.change_1d or 0) > 0 else "波动平稳"),
                tone=vix.tone,
                as_of=vix.as_of,
                data_status=sentiment_group.data_status,
                available=sentiment_group.available,
            )
        )
    else:
        summary.append(_unavailable_summary("volatility", "波动率体制"))

    return summary


# ---------------------------------------------------------------------------
# 细节与工具函数
# ---------------------------------------------------------------------------


def _cnn_comparisons(fear_greed: FearGreedReading) -> list[MonitoringComparison]:
    """四个历史对比点：按当前观测日期自动回算，不写死具体日期。"""
    base = fear_greed.observed_at.date()
    raw = [
        ("上一交易日", fear_greed.previous_close, base - timedelta(days=1)),
        ("一周前", fear_greed.previous_week, base - timedelta(days=7)),
        ("一月前", fear_greed.previous_month, base - timedelta(days=30)),
        ("一年前", fear_greed.previous_year, base - timedelta(days=365)),
    ]
    return [
        MonitoringComparison(
            label=label,
            value=value,
            status=_cnn_status(value) if value is not None else None,
            as_of=when,
        )
        for label, value, when in raw
    ]


def _sentiment_details(
    fear_greed: FearGreedReading | None,
    bars_by_key: Mapping[str, Sequence[PriceBar] | None],
) -> MonitoringDetails:
    comparisons: list[MonitoringComparison] = []
    history: list[MonitoringPoint] = []
    factors: list[MonitoringFactor] = []
    gauge_value: float | None = None
    gauge_label: str | None = None
    if fear_greed is not None:
        gauge_value = float(fear_greed.score)
        gauge_label = _cnn_status(fear_greed.score)
        comparisons = _cnn_comparisons(fear_greed)
        history = [
            MonitoringPoint(observed_at=point.observed_at, value=point.score)
            for point in fear_greed.history
        ]
        factors = [
            MonitoringFactor(
                key=factor.key, label=factor.label, score=factor.score, rating=factor.rating
            )
            for factor in fear_greed.factors
        ]

    term_ratio = None
    term_status = None
    vix_bars = bars_by_key.get("vix")
    vix3m_bars = bars_by_key.get("vix3m")
    if vix_bars and vix3m_bars:
        vix_last = vix_bars[-1].close
        vix3m_last = vix3m_bars[-1].close
        if vix3m_last:
            term_ratio = round(vix_last / vix3m_last, 3)
            if term_ratio > 1.05:
                term_status = "期限倒挂"
            elif term_ratio < 0.95:
                term_status = "期限陡峭"
            else:
                term_status = "期限正常"

    return MonitoringDetails(
        comparisons=comparisons,
        history=history,
        factors=factors,
        gauge_value=gauge_value,
        gauge_label=gauge_label,
        term_ratio=term_ratio,
        term_status=term_status,
    )


def _scalar_metric(
    key: str, label: str, value: object, *, unit: str, tone: str = "neutral"
) -> MonitoringMetric:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return _unavailable_metric(key, label, unit=unit)
    return MonitoringMetric(key=key, label=label, current=float(value), unit=unit, tone=tone)


def _unavailable_metric(key: str, label: str, unit: str | None = None) -> MonitoringMetric:
    return MonitoringMetric(
        key=key,
        label=label,
        unit=unit,
        available=False,
        tone="unavailable",
        display_status="不可用",
        data_status="unavailable",
    )


def _unavailable_summary(key: str, label: str) -> MonitoringSummary:
    return MonitoringSummary(
        key=key,
        label=label,
        display_value="--",
        status="部分数据缺失",
        tone="unavailable",
        data_status="partial",
        available=False,
    )


def _find_metric(group: MonitoringGroup, key: str) -> MonitoringMetric | None:
    for metric in group.metrics:
        if metric.key == key:
            return metric
    return None


def _group_data_status(metrics: Sequence[MonitoringMetric]) -> Literal[
    "available", "partial", "unavailable"
]:
    statuses = [metric.data_status for metric in metrics]
    if statuses and all(status == "available" for status in statuses):
        return "available"
    if any(status == "available" for status in statuses):
        return "partial"
    return "unavailable"


def _group_status_label(data_status: str) -> str:
    return {"available": "数据正常", "partial": "部分数据缺失"}.get(data_status, "不可用")


def _downgrade(status: str) -> str:
    return "partial" if status == "available" else status


def _change(current: float, base: float, mode: str) -> float:
    value = (current / base - 1.0) * 100 if mode == "percent" else current - base
    return round(value, 2)


def _direction(value: float | None, epsilon: float) -> str | None:
    if value is None:
        return None
    if value > epsilon:
        return "rising"
    if value < -epsilon:
        return "falling"
    return "flat"


def _asset_tone(change: float | None) -> str:
    if change is None:
        return "neutral"
    if change > 0:
        return "positive"
    if change < 0:
        return "negative"
    return "neutral"


def _risk_tone(change: float | None) -> str:
    """VIX 上升代表风险升温，语义与资产涨跌相反。"""
    if change is None:
        return "neutral"
    if change > 0:
        return "negative"
    if change < 0:
        return "positive"
    return "neutral"


def _cnn_tone(score: float) -> str:
    if score < 25:
        return "negative"
    if score < 45:
        return "warning"
    if score < 55:
        return "neutral"
    if score < 75:
        return "positive"
    return "warning"


def _cnn_status(score: float) -> str:
    """F&G 标准五档阈值：0-25 恐惧 / 25-45 谨慎 / 45-55 中性 / 55-75 乐观 / 75-100 贪婪。"""
    if score < 25:
        return "恐惧"
    if score < 45:
        return "谨慎"
    if score < 55:
        return "中性"
    if score < 75:
        return "乐观"
    return "贪婪"


def _fmt(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:g}"
