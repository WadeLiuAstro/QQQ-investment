from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Callable

import httpx
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import load_rule_config
from app.db import SnapshotRepository
from app.models import DashboardPayload, SourceStatus
from app.providers.cnn_fear_greed import fetch_fear_greed
from app.providers.macro_calendar import load_macro_events
from app.providers.yahoo import fetch_daily_bars, fetch_quote
from app.services.backtest import run_backtest
from app.services.action_card import build_action_card
from app.services.alerts import build_alerts
from app.services.breadth import build_breadth
from app.services.dashboard import build_dashboard_payload
from app.services.decision import evaluate_decision
from app.services.explanation import build_threshold_matrix
from app.services.export import write_dashboard_json
from app.services.indicators import calculate_indicators
from app.services.session import NY_TZ, is_regular_session_open, session_elapsed_fraction
from app.services.state_history import build_state_history

SYMBOLS = {
    "qqq": "QQQ",
    "qqqe": "QQQE",
    "xlk": "XLK",
    "smh": "SMH",
    "xle": "XLE",
    "xlf": "XLF",
    "ixic": "^IXIC",
    "vix": "^VIX",
    "treasury_10y": "^TNX",
    "dollar_index": "DX-Y.NYB",
}


def refresh_once(
    repository: SnapshotRepository,
    export_path: Path,
    collect: Callable[[DashboardPayload | None], DashboardPayload] | None = None,
) -> DashboardPayload:
    previous = repository.load_latest_payload()
    payload = (collect or collect_dashboard_payload)(previous)
    repository.save_payload(payload)
    repository.record_state(payload)
    alerts = [alert.model_dump() for alert in build_alerts(previous, payload)]
    payload = payload.model_copy(update={"alerts": alerts})
    if payload.decision is not None:
        since = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        history = build_state_history(repository.load_state_history(since_iso=since))
        payload = payload.model_copy(update={"state_history": history.model_dump()})
    repository.save_payload(payload)
    for status in payload.sources.values():
        repository.record_source_status(status)
    write_dashboard_json(payload, export_path)
    return payload


def collect_dashboard_payload(previous: DashboardPayload | None) -> DashboardPayload:
    generated_at = datetime.now(UTC)
    market: dict[str, dict[str, object]] = {}
    sources: dict[str, SourceStatus] = {}
    qqq_bars = None
    qqqe_bars = None
    vix_value = None
    vix_bars = None

    for key, symbol in SYMBOLS.items():
        bars, status = fetch_daily_bars(symbol, "1y")
        sources[f"yahoo_{key}"] = status.model_copy(update={"source": f"yahoo_{key}"})
        if bars:
            market[key] = _market_card(symbol, bars)
            if key == "qqq":
                qqq_bars = bars
            if key == "qqqe":
                qqqe_bars = bars
            if key == "vix":
                vix_value = bars[-1].close
                vix_bars = bars

    quote, quote_status = fetch_quote("QQQ")
    sources["yahoo_quote"] = quote_status
    if quote and "qqq" in market:
        market["qqq"].update(
            {
                "price": quote.price,
                "previous_close": quote.previous_close,
                "is_intraday_estimate": quote.is_intraday_estimate,
            }
        )
    market_open = is_regular_session_open()

    with httpx.Client() as client:
        fear_greed, fear_status = fetch_fear_greed(client)
        events, macro_status = load_macro_events(
            client, date.today(), date.today() + timedelta(days=7)
        )
    sources["cnn_fear_greed"] = fear_status
    sources["macro_calendar"] = macro_status

    decision = None
    backtest = None
    action_card = None
    if qqq_bars:
        volume_fraction = None
        if market_open and qqq_bars[-1].day == datetime.now(NY_TZ).date():
            volume_fraction = session_elapsed_fraction()
        indicators = calculate_indicators(
            qqq_bars,
            intraday_price=quote.price if quote else None,
            volume_elapsed_fraction=volume_fraction,
        )
        indicators = replace(
            indicators,
            vix=vix_value,
            fear_greed=fear_greed.score if fear_greed else None,
        )
        decision = evaluate_decision(indicators, load_rule_config())
        market["qqq"]["indicators"] = asdict(indicators)
        market["qqq"]["threshold_matrix"] = [
            row.model_dump()
            for row in build_threshold_matrix(qqq_bars, vix_bars, indicators, load_rule_config())
        ]
        market["qqq"]["breadth"] = build_breadth(qqq_bars, qqqe_bars).model_dump()
        if fear_greed:
            market["qqq"]["fear_greed"] = {
                "score": fear_greed.score,
                "rating": fear_greed.rating,
                "observed_at": fear_greed.observed_at.isoformat(),
            }
        result = run_backtest(qqq_bars, load_rule_config())
        backtest = {
            "cumulative_return": result.cumulative_return,
            "max_drawdown": result.max_drawdown,
            "turnover": result.turnover,
            "state_counts": result.state_counts,
            "benchmark_return": result.benchmark_return,
        }
        action_card = build_action_card(
            indicators, decision, load_rule_config(), sources
        ).model_dump()

    return build_dashboard_payload(
        generated_at=generated_at,
        sources=sources,
        market=market if market else None,
        decision=decision,
        events=events,
        backtest=backtest,
        action_card=action_card,
        previous=previous,
    )


def _market_card(symbol: str, bars: list[object]) -> dict[str, object]:
    latest = bars[-1]
    previous = bars[-2] if len(bars) > 1 else None
    daily_change = round((latest.close / previous.close - 1.0) * 100, 2) if previous else None
    card = {
        "symbol": symbol,
        "price": latest.close,
        "official_close": latest.close,
        "official_close_day": latest.day.isoformat(),
        "daily_change_pct": daily_change,
        "five_day_closes": [bar.close for bar in bars[-5:]],
    }
    if symbol == "^IXIC":
        card["daily_change_points"] = round(latest.close - previous.close, 2) if previous else None
        card["candles"] = [
            {"time": bar.day.isoformat(), "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close}
            for bar in bars
            if None not in (bar.open, bar.high, bar.low)
        ]
    return card

def create_refresh_scheduler(
    repository: SnapshotRepository, export_path: Path
) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="America/New_York")
    scheduler.add_job(
        refresh_once,
        trigger="interval",
        minutes=15,
        args=[repository, export_path],
        id="dashboard_refresh",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler