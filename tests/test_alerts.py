from datetime import UTC, datetime, timedelta

from app.models import DashboardPayload, Decision, MacroEvent, SourceStatus
from app.services.alerts import build_alerts


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


def matrix_row(rule: str, distance: float | None) -> dict:
    return {
        "rule": rule,
        "label": rule,
        "current": 1.0,
        "condition": "≤ 1",
        "distance": distance,
        "unit": "点",
        "direction": None,
        "available": distance is not None,
        "note": None,
    }


def payload(
    state: str | None = None,
    distances: dict[str, float] | None = None,
    unavailable: tuple[str, ...] = (),
    events: list[MacroEvent] | None = None,
    alerts: list[dict] | None = None,
) -> DashboardPayload:
    sources = {name: source(name, name not in unavailable) for name in ("yahoo_qqq", "cnn_fear_greed")}
    matrix = [matrix_row(rule, (distances or {}).get(rule)) for rule in ("rsi2_oversold", "rsi6_oversold", "drawdown_risk", "vix_high", "volume_ratio_high")]
    return DashboardPayload(
        generated_at=datetime.now(UTC),
        sources=sources,
        decision=decision(state) if state else None,
        market={"qqq": {"threshold_matrix": matrix}},
        events=events or [],
        alerts=alerts,
    )


def event(kind: str, days_ahead: int) -> MacroEvent:
    return MacroEvent(
        kind=kind,
        title=kind,
        event_at=datetime.now(UTC) + timedelta(days=days_ahead),
        source="test",
    )


def test_state_switch_alert_on_change() -> None:
    previous = payload(state="neutral")
    current = payload(state="constructive")

    alerts = build_alerts(previous, current)

    assert [a.key for a in alerts] == ["state_switch:constructive"]
    assert alerts[0].kind == "state_switch"
    assert "建设性加仓" in alerts[0].detail


def test_no_state_switch_alert_when_same_state() -> None:
    alerts = build_alerts(payload(state="neutral"), payload(state="neutral"))

    assert alerts == []


def test_near_threshold_alert_when_entering_buffer() -> None:
    previous = payload(distances={"vix_high": 5.0})
    current = payload(distances={"vix_high": 2.9})

    alerts = build_alerts(previous, current)

    assert [a.key for a in alerts] == ["near:vix_high"]


def test_near_threshold_boundary_equals_buffer_is_near() -> None:
    alerts = build_alerts(
        payload(distances={"vix_high": 6.0}),
        payload(distances={"vix_high": 3.0}),
    )
    assert [a.key for a in alerts] == ["near:vix_high"]


def test_no_near_threshold_alert_when_already_near() -> None:
    alerts = build_alerts(
        payload(distances={"vix_high": 2.9}),
        payload(distances={"vix_high": 2.5}),
    )
    assert alerts == []


def test_multiple_risks_alert_when_entering_defensive() -> None:
    alerts = build_alerts(payload(state="constructive"), payload(state="defensive"))

    assert [a.key for a in alerts] == ["state_switch:defensive", "multiple_risks"]
    assert "两项及以上风险" in alerts[1].detail


def test_no_multiple_risks_alert_when_already_defensive() -> None:
    alerts = build_alerts(payload(state="defensive"), payload(state="defensive"))

    assert alerts == []


def test_source_stale_alert_on_consecutive_failure() -> None:
    previous = payload(unavailable=("cnn_fear_greed",))
    current = payload(unavailable=("cnn_fear_greed",))

    alerts = build_alerts(previous, current)

    assert [a.key for a in alerts] == ["source:cnn_fear_greed"]


def test_no_source_stale_alert_on_first_failure() -> None:
    alerts = build_alerts(
        payload(unavailable=()),
        payload(unavailable=("cnn_fear_greed",)),
    )
    assert alerts == []


def test_event_approaching_alert_within_three_days() -> None:
    alerts = build_alerts(
        payload(),
        payload(events=[event("fomc", 2), event("cpi", 5)]),
    )

    assert [a.key for a in alerts] == [f"event:fomc:{event('fomc', 2).event_at.date().isoformat()}"]
    assert alerts[0].kind == "event_approaching"


def test_previous_none_only_fires_event_alerts() -> None:
    alerts = build_alerts(
        None,
        payload(
            state="defensive",
            unavailable=("cnn_fear_greed",),
            events=[event("nfp", 1)],
        ),
    )

    assert [a.key for a in alerts] == [f"event:nfp:{event('nfp', 1).event_at.date().isoformat()}"]


def test_alerts_deduped_by_key_from_previous() -> None:
    previous = payload(
        alerts=[{"key": "near:vix_high", "kind": "near_threshold", "title": "t", "detail": "d"}]
    )
    current = payload(distances={"vix_high": 2.9})

    alerts = build_alerts(previous, current)

    assert alerts == []
