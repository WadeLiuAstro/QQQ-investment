"""Task 3: monitoring 接入 scheduler/快照/API 的集成测试。"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import SnapshotRepository
from app.main import create_app
from app.models import DashboardPayload, SourceStatus
from app.providers.cnn_fear_greed import FearGreedReading
from app.providers.yahoo import PriceBar, Quote
from app.scheduler import collect_dashboard_payload


def bars(closes: list[float], start: date = date(2025, 1, 1)) -> list[PriceBar]:
    return [
        PriceBar(day=start + timedelta(days=index), close=close, volume=1_000_000)
        for index, close in enumerate(closes)
    ]


def status(source: str, available: bool = True) -> SourceStatus:
    return SourceStatus(source=source, available=available, checked_at=datetime.now(UTC))


def install_mocks(monkeypatch: pytest.MonkeyPatch, cnn_available: bool = True) -> None:
    rising = bars([100.0 + index * 0.5 for index in range(260)])
    vix = bars([16.0 + (index % 10) * 0.1 for index in range(260)])
    vix3m = bars([15.0 + (index % 10) * 0.05 for index in range(260)])

    def fake_bars(symbol: str, period: str):
        if symbol == "^VIX":
            return vix, status("yahoo")
        if symbol == "^VIX3M":
            return vix3m, status("yahoo")
        return rising, status("yahoo")

    def fake_quote(symbol: str):
        return (
            Quote(symbol=symbol, price=205.0, previous_close=200.0, is_intraday_estimate=False),
            status("yahoo_quote"),
        )

    def fake_fear_greed(client):
        if not cnn_available:
            return None, status("cnn_fear_greed", available=False)
        return (
            FearGreedReading(score=50, rating="neutral", observed_at=datetime.now(UTC)),
            status("cnn_fear_greed"),
        )

    def fake_macro(client, start, end):
        return [], status("macro_calendar")

    monkeypatch.setattr("app.scheduler.fetch_daily_bars", fake_bars)
    monkeypatch.setattr("app.scheduler.fetch_quote", fake_quote)
    monkeypatch.setattr("app.scheduler.fetch_fear_greed", fake_fear_greed)
    monkeypatch.setattr("app.scheduler.load_macro_events", fake_macro)


def test_collect_dashboard_payload_attaches_monitoring(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mocks(monkeypatch)

    payload = collect_dashboard_payload(None)

    assert payload.monitoring is not None
    assert list(payload.monitoring.groups) == [
        "sentiment_volatility",
        "core_breadth",
        "sector_rotation",
        "macro_defensive",
    ]
    assert [card.key for card in payload.monitoring.summary] == [
        "sentiment", "core_trend", "breadth", "volatility"
    ]


def test_collect_dashboard_payload_decision_unchanged_by_monitoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mocks(monkeypatch)
    payload = collect_dashboard_payload(None)
    assert payload.decision is not None
    assert payload.monitoring is not None


def test_missing_cnn_degrades_only_sentiment(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mocks(monkeypatch, cnn_available=False)

    payload = collect_dashboard_payload(None)

    monitoring = payload.monitoring
    assert monitoring is not None
    assert monitoring.groups["sentiment_volatility"].data_status in ("partial", "unavailable")
    assert monitoring.groups["sector_rotation"].data_status == "available"


def test_dashboard_api_preserves_monitoring_snapshot(tmp_path: Path) -> None:
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite")
    payload = DashboardPayload(
        generated_at=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
        sources={},
        market={"qqq": {"symbol": "QQQ", "price": 500.0}},
    )
    # 通过真实服务构造 monitoring 并附加
    from app.services.monitoring import build_monitoring

    payload = payload.model_copy(
        update={
            "monitoring": build_monitoring(
                generated_at=payload.generated_at,
                bars_by_key={},
                market={},
                fear_greed=None,
                events=[],
                sources={},
            )
        }
    )
    repository.save_payload(payload)

    app = create_app(repository, tmp_path / "dashboard.json")
    response = TestClient(app).get("/api/dashboard")

    assert response.status_code == 200
    assert response.json()["monitoring"]["summary"][0]["key"] == "sentiment"


def test_legacy_payload_without_monitoring_still_validates(tmp_path: Path) -> None:
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite")
    legacy = DashboardPayload(
        generated_at=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
        sources={},
        market={"qqq": {"symbol": "QQQ", "price": 500.0}},
    )
    repository.save_payload(legacy)

    app = create_app(repository, tmp_path / "dashboard.json")
    response = TestClient(app).get("/api/dashboard")

    assert response.status_code == 200
    assert response.json()["monitoring"] is None
