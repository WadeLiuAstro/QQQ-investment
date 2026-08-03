from datetime import datetime

from app.models import DashboardPayload, Decision, MacroEvent, SourceStatus


def build_dashboard_payload(
    *,
    generated_at: datetime,
    sources: dict[str, SourceStatus],
    market: dict[str, dict[str, object]] | None,
    decision: Decision | None = None,
    events: list[MacroEvent] | None = None,
    backtest: dict[str, object] | None = None,
    previous: DashboardPayload | None = None,
) -> DashboardPayload:
    resolved_market = market
    resolved_events = events
    resolved_backtest = backtest
    resolved_sources = dict(sources)
    if previous is not None:
        if resolved_market is None:
            resolved_market = previous.market
            _mark_failed_sources_stale(resolved_sources)
        if resolved_events is None:
            resolved_events = previous.events
        if resolved_backtest is None:
            resolved_backtest = previous.backtest
    return DashboardPayload(
        generated_at=generated_at,
        sources=resolved_sources,
        decision=decision,
        market=resolved_market or {},
        events=resolved_events or [],
        backtest=resolved_backtest,
    )


def _mark_failed_sources_stale(sources: dict[str, SourceStatus]) -> None:
    for source, status in sources.items():
        if not status.available:
            sources[source] = status.model_copy(update={"stale": True})
