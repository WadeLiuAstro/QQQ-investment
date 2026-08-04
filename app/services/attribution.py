"""S2a: 大跌检测与证据集组装（体系 §5）。

触发条件：单日跌幅 ≥ 2%，或回撤进入新的 5% 档位（距 52 周高点）。
证据集：VIX 水平与跳升、市场宽度、事件日历、回撤深度与速度。
"""

import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Sequence

from app.models import MacroEvent
from app.providers.yahoo import PriceBar

_DAILY_DROP_PCT = -2.0
_DRAWDOWN_TIER_PCT = 5.0
_SPIKE_WINDOW = 5
_EVENT_WINDOW_DAYS = 3
_MA_WINDOW = 200


@dataclass(frozen=True)
class CrashEvidence:
    available: bool
    triggered: bool = False
    day: date | None = None
    daily_change_pct: float | None = None
    drawdown_pct: float | None = None
    drawdown_speed_days: int | None = None
    vix: float | None = None
    vix_spike_pct: float | None = None
    rs_20d: float | None = None
    rs_5d: float | None = None
    pending_events: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass(frozen=True)
class AttributionGate:
    status: str  # "open" | "half" | "frozen"
    reason: str
    pending: bool = False
    deadline: datetime | None = None


_PENDING_WINDOW = timedelta(hours=48)


def evaluate_attribution_gate(
    evidence: CrashEvidence,
    decision: dict[str, object] | None = None,
    now: datetime | None = None,
) -> AttributionGate:
    """按归因拍板状态输出加仓通道闸门（体系 §5）。

    - 未触发大跌：放行
    - 触发未拍板：减半执行（48 小时倒计时）
    - 流动性恐慌：放行
    - 结构性风险：冻结加仓
    - 待观察：减半执行，48 小时后复核
    """
    reference = now or datetime.now(UTC)
    if not evidence.triggered:
        return AttributionGate(status="open", reason="无大跌触发，加仓通道正常")
    if decision is None:
        return AttributionGate(
            status="half",
            reason="大跌已触发，待归因拍板（超时未拍板=减半执行）",
            pending=True,
            deadline=reference + _PENDING_WINDOW,
        )
    classification = decision.get("classification")
    if classification == "liquidity_panic":
        return AttributionGate(status="open", reason="归因：流动性恐慌，正常执行加仓")
    if classification == "structural":
        return AttributionGate(status="frozen", reason="归因：结构性风险，冻结加仓")
    if classification == "watch":
        deadline = None
        expires = decision.get("expires_at")
        if expires:
            deadline = datetime.fromisoformat(str(expires))
        return AttributionGate(
            status="half",
            reason="归因：待观察，减半执行，48 小时后复核",
            deadline=deadline,
        )
    return AttributionGate(status="half", reason="归因分类未知，减半执行")


def build_evidence_set(
    qqq_bars: Sequence[PriceBar],
    vix_bars: Sequence[PriceBar] | None = None,
    qqqe_bars: Sequence[PriceBar] | None = None,
    events: Sequence[MacroEvent] | None = None,
    today: date | None = None,
) -> CrashEvidence:
    """评估是否触发大跌，并组装归因证据集。"""
    if not qqq_bars or len(qqq_bars) < 2:
        return CrashEvidence(available=False, note="QQQ 数据不足")

    closes = [bar.close for bar in qqq_bars]
    price = closes[-1]
    previous = closes[-2]
    daily_change = round((price / previous - 1.0) * 100, 2)

    window = closes[-252:] if len(closes) >= 252 else closes
    peak = max(window)
    drawdown_pct = round((price / peak - 1.0) * 100, 2) if peak else None
    drawdown_speed_days = None
    if peak:
        peak_idx = window.index(peak)
        drawdown_speed_days = len(window) - 1 - peak_idx

    # 新台阶检测：此前最低回撤档位 vs 当前档位
    tier_crossed = False
    if drawdown_pct is not None:
        prior_low = min(window[:-1]) if len(window) > 1 else None
        if prior_low is not None:
            prior_tier = _tier((prior_low / peak - 1.0) * 100)
            current_tier = _tier(drawdown_pct)
            tier_crossed = current_tier < prior_tier

    triggered = daily_change <= _DAILY_DROP_PCT or tier_crossed

    # 证据：VIX 水平与 5 日跳升
    vix = None
    vix_spike = None
    if vix_bars:
        vix_closes = [bar.close for bar in vix_bars]
        vix = vix_closes[-1]
        if len(vix_closes) > _SPIKE_WINDOW:
            base = vix_closes[-_SPIKE_WINDOW - 1]
            if base > 0:
                vix_spike = round((vix / base - 1.0) * 100, 2)

    # 证据：市场宽度相对强弱
    rs_20d = _rs(qqq_bars, qqqe_bars, 20)
    rs_5d = _rs(qqq_bars, qqqe_bars, 5)

    # 证据：事件日历（3 天内临近）
    reference_day = today or datetime.now(UTC).date()
    pending_events = []
    for event in events or []:
        delta = (event.event_at.date() - reference_day).days
        if 0 <= delta <= _EVENT_WINDOW_DAYS:
            pending_events.append(event.title)

    return CrashEvidence(
        available=True,
        triggered=triggered,
        day=qqq_bars[-1].day,
        daily_change_pct=daily_change,
        drawdown_pct=drawdown_pct,
        drawdown_speed_days=drawdown_speed_days,
        vix=vix,
        vix_spike_pct=vix_spike,
        rs_20d=rs_20d,
        rs_5d=rs_5d,
        pending_events=pending_events,
    )


def _tier(drawdown_pct: float) -> int:
    # 先取整到两位小数消除浮点误差（-10.0 不应被 ceil 抬到 -1 档）；
    # ceil 使 -10.0%~-14.9% 归入 -10% 档，-15.0%~-19.9% 归入 -15% 档
    return math.ceil(round(drawdown_pct, 2) / _DRAWDOWN_TIER_PCT)


def _rs(
    qqq_bars: Sequence[PriceBar], qqqe_bars: Sequence[PriceBar] | None, window: int
) -> float | None:
    if not qqqe_bars or len(qqq_bars) < window + 1 or len(qqqe_bars) < window + 1:
        return None
    qqq_return = qqq_bars[-1].close / qqq_bars[-window - 1].close - 1.0
    qqqe_return = qqqe_bars[-1].close / qqqe_bars[-window - 1].close - 1.0
    return round((qqqe_return - qqq_return) * 100, 2)
