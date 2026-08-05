from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Callable

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import load_rule_config
from app.db import SnapshotRepository
from app.models import DashboardPayload, IntradayWatch, SourceStatus
from app.providers.cnn_fear_greed import fetch_fear_greed
from app.providers.macro_calendar import load_macro_events
from app.providers.yahoo import Quote, fetch_daily_bars, fetch_quote
from app.services.backtest import run_backtest
from app.services.action_card import build_action_card
from app.services.alerts import build_alerts
from app.services.attribution import (
    CrashEvidence,
    build_evidence_set,
    evaluate_attribution_gate,
)
from app.services.breadth import build_breadth
from app.services.dashboard import build_dashboard_payload
from app.services.decision import evaluate_decision
from app.services.explanation import build_threshold_matrix
from app.services.export import write_dashboard_json
from app.services.indicators import calculate_indicators
from app.services.intraday_guard import build_circuit_alerts, detect_circuit_events
from app.services.monitoring import build_monitoring, mark_monitoring_stale
from app.services.session import (
    NY_TZ,
    expected_bar_date,
    is_regular_session_open,
    session_elapsed_fraction,
    trading_day_lag,
)
from app.services.state_history import build_state_history
from app.services.structural import compute_structural_score
from app.services.trend import evaluate_trend

# 守护用默认报价抓取（别名便于测试注入，与 fetch_quote 为同一函数）
fetch_quote_default = fetch_quote

SYMBOLS = {
    "qqq": "QQQ",
    "qqqe": "QQQE",
    "xlk": "XLK",
    "smh": "SMH",
    "xle": "XLE",
    "xlf": "XLF",
    "ixic": "^IXIC",
    "vix": "^VIX",
    "vix3m": "^VIX3M",
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
    payload = attach_attribution_gate(payload, repository)
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
    vix3m_bars = None
    bars_by_key: dict[str, object] = {}

    for key, symbol in SYMBOLS.items():
        # 结构评分需要 252 根 52 周窗口，QQQ/QQQE 取 2y 保证足够历史
        period = "2y" if key in ("qqq", "qqqe") else "1y"
        bars, status = fetch_daily_bars(symbol, period)
        sources[f"yahoo_{key}"] = status.model_copy(update={"source": f"yahoo_{key}"})
        if bars:
            bars_by_key[key] = bars
            market[key] = _market_card(
                symbol, bars, expected=expected_bar_date(datetime.now(NY_TZ))
            )
            if key == "qqq":
                qqq_bars = bars
            if key == "qqqe":
                qqqe_bars = bars
            if key == "vix":
                vix_value = bars[-1].close
                vix_bars = bars
            if key == "vix3m":
                vix3m_bars = bars

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
        market["qqq"]["trend"] = asdict(
            evaluate_trend(qqq_bars, previous_regime=_previous_trend_regime(previous))
        )
        market["qqq"]["structural_risk"] = asdict(
            compute_structural_score(qqq_bars, qqqe_bars, vix_bars, vix3m_bars)
        )
        market["qqq"]["attribution"] = {
            "evidence": asdict(build_evidence_set(qqq_bars, vix_bars, qqqe_bars, events))
        }
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

    monitoring = None
    try:
        monitoring = build_monitoring(
            generated_at=generated_at,
            bars_by_key=bars_by_key,
            market=market,
            fear_greed=fear_greed,
            events=events,
            sources=sources,
            previous=previous.monitoring if previous else None,
        )
    except Exception:
        if previous is not None and previous.monitoring is not None:
            monitoring = mark_monitoring_stale(previous.monitoring, generated_at)
        else:
            monitoring = None

    return build_dashboard_payload(
        generated_at=generated_at,
        sources=sources,
        market=market if market else None,
        decision=decision,
        events=events,
        backtest=backtest,
        action_card=action_card,
        previous=previous,
        monitoring=monitoring,
    )


def _previous_trend_regime(previous: DashboardPayload | None) -> str | None:
    """从上一快照读取 MA200 趋势状态，供状态机维持空头环境。"""
    if previous is None or previous.market is None:
        return None
    qqq = previous.market.get("qqq")
    trend = qqq.get("trend") if qqq else None
    if isinstance(trend, dict):
        return trend.get("regime")
    return None


def attach_attribution_gate(
    payload: DashboardPayload, repository: SnapshotRepository
) -> DashboardPayload:
    """把归因闸门（gate）与最近拍板写入 payload.market.qqq.attribution。"""
    if payload.market is None:
        return payload
    qqq = payload.market.get("qqq")
    attribution = qqq.get("attribution") if qqq else None
    if not isinstance(attribution, dict):
        return payload
    evidence_dict = attribution.get("evidence")
    if not isinstance(evidence_dict, dict):
        return payload

    # day 经 JSON 序列化后为 ISO 字符串，还原为 date
    day_raw = evidence_dict.get("day")
    day = date.fromisoformat(day_raw) if isinstance(day_raw, str) else day_raw
    evidence = CrashEvidence(**{**evidence_dict, "day": day})
    incident_key = evidence.day.isoformat() if evidence.day else "unknown"
    decision = repository.load_attribution_decision(incident_key)
    gate = evaluate_attribution_gate(evidence, decision)

    if evidence.triggered and decision is None:
        repository.append_decision_log(
            category="signal",
            incident_key=incident_key,
            content={
                "kind": "crash_triggered",
                "daily_change_pct": evidence.daily_change_pct,
                "drawdown_pct": evidence.drawdown_pct,
            },
        )

    updated_attribution = {
        **attribution,
        "gate": asdict(gate),
        "decision": decision,
    }
    updated_qqq = {**qqq, "attribution": updated_attribution}
    return payload.model_copy(update={"market": {**payload.market, "qqq": updated_qqq}})


def _market_card(
    symbol: str, bars: list[object], expected: date | None = None
) -> dict[str, object]:
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
        "stale_lag": trading_day_lag(latest.day, expected) if expected else None,
    }
    if symbol == "^IXIC":
        card["daily_change_points"] = round(latest.close - previous.close, 2) if previous else None
        card["candles"] = [
            {"time": bar.day.isoformat(), "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close}
            for bar in bars
            if None not in (bar.open, bar.high, bar.low)
        ]
    return card

def run_intraday_guard(
    repository: SnapshotRepository,
    export_path: Path,
    fetch_quote: Callable[[str], tuple[Quote | None, SourceStatus]] = fetch_quote_default,
    now: datetime | None = None,
) -> DashboardPayload | None:
    """盘中轻量守护：只追加熔断预警并刷新 intraday_watch。

    绝不重算正式决策，也不写状态历史；非交易时段或无日频快照时 no-op。
    """
    if now is None:
        now = datetime.now(NY_TZ)
    if not is_regular_session_open(now):
        return None
    payload = repository.load_latest_payload()
    if payload is None:
        return None

    qqq_quote, _ = fetch_quote("QQQ")
    vix_quote, _ = fetch_quote("^VIX")

    findings = detect_circuit_events(qqq_quote, vix_quote)
    new_alerts = build_circuit_alerts(findings, day=now.astimezone(NY_TZ).date())

    # 去重：已有 key 的预警不重复追加
    alerts = list(payload.alerts or [])
    existing_keys = {alert.get("key") for alert in alerts}
    for alert in new_alerts:
        dumped = alert.model_dump()
        if dumped["key"] not in existing_keys:
            alerts.append(dumped)
            existing_keys.add(dumped["key"])

    watch = IntradayWatch(
        checked_at=now.astimezone(UTC),
        qqq_price=qqq_quote.price if qqq_quote else None,
        qqq_change_pct=_quote_change_pct(qqq_quote),
        vix=vix_quote.price if vix_quote else None,
        vix_change_pct=_quote_change_pct(vix_quote),
        triggered=bool(findings),
    )

    # 只更新 alerts 与 intraday_watch，其余字段（含 decision/market/snapshot_kind/generated_at）保持原样
    updated = payload.model_copy(update={"alerts": alerts, "intraday_watch": watch})
    repository.save_payload(updated)
    write_dashboard_json(updated, export_path)
    return updated


def _quote_change_pct(quote: Quote | None) -> float | None:
    """相对昨收的变化百分比；报价或昨收无效时返回 None。"""
    if quote is None or not quote.previous_close:
        return None
    return (quote.price - quote.previous_close) / quote.previous_close * 100


def create_refresh_scheduler(
    repository: SnapshotRepository, export_path: Path
) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="America/New_York")
    # 日频全量刷新：工作日收盘后 16:35 产出正式信号
    scheduler.add_job(
        refresh_once,
        trigger=CronTrigger(day_of_week="mon-fri", hour=16, minute=35),
        args=[repository, export_path],
        id="daily_refresh",
        replace_existing=True,
    )
    # 盘中轻量守护：每 15 分钟只追加熔断提醒，不重算正式决策
    scheduler.add_job(
        run_intraday_guard,
        trigger="interval",
        minutes=15,
        args=[repository, export_path],
        id="intraday_guard",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler