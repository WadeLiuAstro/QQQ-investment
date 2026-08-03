from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Callable

import httpx

from app.config import load_rule_config
from app.db import SnapshotRepository
from app.models import DashboardPayload, SourceStatus
from app.providers.cnn_fear_greed import fetch_fear_greed
from app.providers.macro_calendar import load_macro_events
from app.providers.yahoo import fetch_daily_bars, fetch_quote
from app.services.backtest import run_backtest
from app.services.dashboard import build_dashboard_payload
from app.services.decision import evaluate_decision
from app.services.export import write_dashboard_json
from app.services.indicators import calculate_indicators

SYMBOLS = {
    "qqq": "QQQ",
    "xlk": "XLK",
    "smh": "SMH",
    "xle": "XLE",
    "xlf": "XLF",
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
    for status in payload.sources.values():
        repository.record_source_status(status)
    write_dashboard_json(payload, export_path)
    return payload


def collect_dashboard_payload(previous: DashboardPayload | None) -> DashboardPayload:
    generated_at = datetime.now(UTC)
    market: dict[str, dict[str, object]] = {}
    sources: dict[str, SourceStatus] = {}
    qqq_bars = None
    vix_value = None

    for key, symbol in SYMBOLS.items():
        bars, status = fetch_daily_bars(symbol, "1y")
        sources[f"yahoo_{key}"] = status.model_copy(update={"source": f"yahoo_{key}"})
        if bars:
            market[key] = _market_card(symbol, bars)
            if key == "qqq":
                qqq_bars = bars
            if key == "vix":
                vix_value = bars[-1].close

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

    with httpx.Client() as client:
        fear_greed, fear_status = fetch_fear_greed(client)
        events, macro_status = load_macro_events(
            client, date.today(), date.today() + timedelta(days=7)
        )
    sources["cnn_fear_greed"] = fear_status
    sources["macro_calendar"] = macro_status

    decision = None
    backtest = None
    if qqq_bars:
        indicators = calculate_indicators(
            qqq_bars,
            intraday_price=quote.price if quote else None,
        )
        indicators = replace(
            indicators,
            vix=vix_value,
            fear_greed=fear_greed.score if fear_greed else None,
        )
        decision = evaluate_decision(indicators, load_rule_config())
        market["qqq"]["indicators"] = asdict(indicators)
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

    return build_dashboard_payload(
        generated_at=generated_at,
        sources=sources,
        market=market if market else None,
        decision=decision,
        events=events,
        backtest=backtest,
        previous=previous,
    )


def _market_card(symbol: str, bars: list[object]) -> dict[str, object]:
    latest = bars[-1]
    previous = bars[-2] if len(bars) > 1 else None
    daily_change = (
        round((latest.close / previous.close - 1.0) * 100, 2) if previous else None
    )
    return {
        "symbol": symbol,
        "price": latest.close,
        "official_close": latest.close,
        "official_close_day": latest.day.isoformat(),
        "daily_change_pct": daily_change,
        "five_day_closes": [bar.close for bar in bars[-5:]],
    }
