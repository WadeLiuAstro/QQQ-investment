from datetime import UTC, datetime
from typing import Callable

from app.models import Alert, DashboardPayload

# 指标进入"阈值附近"的缓冲定义（距离 ≤ 缓冲即视为附近）
_NEAR_BUFFERS = {
    "rsi2_oversold": 5.0,
    "rsi6_oversold": 5.0,
    "drawdown_risk": 2.0,
    "vix_high": 3.0,
    "volume_ratio_high": 0.3,
}

_HIGH_IMPACT_EVENTS = ("fomc", "nfp", "cpi")
_EVENT_WINDOW_DAYS = 3

_STATE_NAMES = {
    "defensive": "防御",
    "cautious": "谨慎",
    "neutral": "中性",
    "constructive": "建设性加仓",
    "opportunity": "加仓机会",
}

_SOURCE_LABELS = {
    "yahoo_qqq": "QQQ 行情",
    "yahoo_ixic": "纳指 K 线",
    "yahoo_vix": "VIX",
    "cnn_fear_greed": "恐慌贪婪指数",
    "macro_calendar": "宏观日历",
}


def build_alerts(
    previous: DashboardPayload | None, current: DashboardPayload
) -> list[Alert]:
    """对比相邻两次快照，产出边沿事件类提醒（低噪声）。

    除事件临近外，其余提醒都需要 previous 快照；同一 key 已在上次 alerts
    中出现则不再重复。
    """
    alerts: list[Alert] = []
    seen = {item["key"] for item in previous.alerts} if previous and previous.alerts else set()

    def add(alert: Alert) -> None:
        if alert.key not in seen:
            seen.add(alert.key)
            alerts.append(alert)

    if previous is not None:
        _state_alerts(previous, current, add)
        _near_threshold_alerts(previous, current, add)
        _source_stale_alerts(previous, current, add)
    _event_alerts(current, add)
    return alerts


def _state_alerts(
    previous: DashboardPayload,
    current: DashboardPayload,
    add: Callable[[Alert], None],
) -> None:
    if current.decision is None or previous.decision is None:
        return
    current_state = current.decision.state
    previous_state = previous.decision.state
    if current_state != previous_state:
        add(
            Alert(
                key=f"state_switch:{current_state}",
                kind="state_switch",
                title="状态切换",
                detail=f"状态由 {_STATE_NAMES.get(previous_state, previous_state)} 切换为 {_STATE_NAMES.get(current_state, current_state)}",
            )
        )
    if current_state == "defensive" and previous_state != "defensive":
        add(
            Alert(
                key="multiple_risks",
                kind="multiple_risks",
                title="多项风险同时触发",
                detail="两项及以上风险条件同时触发，进入防御状态",
            )
        )


def _near_threshold_alerts(
    previous: DashboardPayload,
    current: DashboardPayload,
    add: Callable[[Alert], None],
) -> None:
    previous_rows = _matrix_by_rule(previous)
    for rule, buffer in _NEAR_BUFFERS.items():
        row = _matrix_by_rule(current).get(rule)
        if not row or row.get("distance") is None:
            continue
        distance = float(row["distance"])
        previous_row = previous_rows.get(rule)
        previous_distance = (
            float(previous_row["distance"])
            if previous_row and previous_row.get("distance") is not None
            else None
        )
        if distance <= buffer and (previous_distance is None or previous_distance > buffer):
            add(
                Alert(
                    key=f"near:{rule}",
                    kind="near_threshold",
                    title=f"{row.get('label', rule)} 接近阈值",
                    detail=f"距离触发仅剩 {distance:g} {row.get('unit', '')}",
                )
            )


def _source_stale_alerts(
    previous: DashboardPayload,
    current: DashboardPayload,
    add: Callable[[Alert], None],
) -> None:
    for name, status in current.sources.items():
        if status.available:
            continue
        previous_status = previous.sources.get(name)
        if previous_status is not None and not previous_status.available:
            add(
                Alert(
                    key=f"source:{name}",
                    kind="source_stale",
                    title=f"{_SOURCE_LABELS.get(name, name)} 持续不可用",
                    detail="连续刷新失败，请检查数据源",
                )
            )


def _event_alerts(
    current: DashboardPayload, add: Callable[[Alert], None]
) -> None:
    today = datetime.now(UTC).date()
    for event in current.events:
        if event.kind not in _HIGH_IMPACT_EVENTS:
            continue
        days_left = (event.event_at.date() - today).days
        if 0 <= days_left <= _EVENT_WINDOW_DAYS:
            add(
                Alert(
                    key=f"event:{event.kind}:{event.event_at.date().isoformat()}",
                    kind="event_approaching",
                    title=f"{event.title} 临近",
                    detail=f"{event.event_at.date().isoformat()} 公布，剩余 {days_left} 天",
                )
            )


def _matrix_by_rule(payload: DashboardPayload) -> dict[str, dict[str, object]]:
    rows = payload.market.get("qqq", {}).get("threshold_matrix", [])
    return {row["rule"]: row for row in rows if isinstance(row, dict)}
