from datetime import datetime

from app.models import (
    DashboardPayload,
    Decision,
    MacroEvent,
    MonitoringPayload,
    SourceStatus,
)


def build_dashboard_payload(
    *,
    generated_at: datetime,
    sources: dict[str, SourceStatus],
    market: dict[str, dict[str, object]] | None,
    decision: Decision | None = None,
    events: list[MacroEvent] | None = None,
    backtest: dict[str, object] | None = None,
    action_card: dict[str, object] | None = None,
    previous: DashboardPayload | None = None,
    monitoring: MonitoringPayload | None = None,
) -> DashboardPayload:
    resolved_market = market
    resolved_events = events
    resolved_backtest = backtest
    resolved_action_card = action_card
    resolved_monitoring = monitoring
    resolved_sources = dict(sources)
    if previous is not None:
        if resolved_market is None:
            resolved_market = previous.market
            _mark_failed_sources_stale(resolved_sources)
        else:
            _reuse_failed_market_cards(resolved_market, previous.market, resolved_sources)
        if resolved_events is None:
            resolved_events = previous.events
        if resolved_backtest is None:
            resolved_backtest = previous.backtest
        if resolved_action_card is None:
            resolved_action_card = previous.action_card
        if resolved_monitoring is None:
            resolved_monitoring = previous.monitoring
    return DashboardPayload(
        generated_at=generated_at,
        sources=resolved_sources,
        decision=decision,
        market=resolved_market or {},
        events=resolved_events or [],
        backtest=resolved_backtest,
        action_card=resolved_action_card,
        monitoring=resolved_monitoring,
    )




def _reuse_failed_market_cards(
    market: dict[str, dict[str, object]],
    previous_market: dict[str, dict[str, object]],
    sources: dict[str, SourceStatus],
) -> None:
    for source, market_key in {"yahoo_ixic": "ixic"}.items():
        status = sources.get(source)
        if status is not None and not status.available and market_key not in market:
            previous_card = previous_market.get(market_key)
            if previous_card is not None:
                market[market_key] = previous_card
                sources[source] = status.model_copy(update={"stale": True})


def _mark_failed_sources_stale(sources: dict[str, SourceStatus]) -> None:
    for source, status in sources.items():
        if not status.available:
            sources[source] = status.model_copy(update={"stale": True})
