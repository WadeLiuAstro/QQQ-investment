from datetime import UTC, datetime

from app.models import DashboardPayload, SourceStatus
from app.services.dashboard import build_dashboard_payload


def test_missing_market_data_reuses_previous_value_and_marks_source_stale() -> None:
    timestamp = datetime(2026, 8, 3, tzinfo=UTC)
    previous = DashboardPayload(
        generated_at=timestamp,
        sources={
            "yahoo": SourceStatus(source="yahoo", available=True, checked_at=timestamp)
        },
        market={"qqq": {"symbol": "QQQ", "price": 500.0}},
    )
    failed_status = SourceStatus(
        source="yahoo", available=False, checked_at=timestamp, message="timeout"
    )

    payload = build_dashboard_payload(
        generated_at=timestamp,
        sources={"yahoo": failed_status},
        market=None,
        previous=previous,
    )

    assert payload.market["qqq"]["price"] == 500.0
    assert payload.sources["yahoo"].available is False
    assert payload.sources["yahoo"].stale is True


def test_missing_ixic_reuses_its_previous_snapshot_without_replacing_other_market_data() -> None:
    timestamp = datetime(2026, 8, 3, tzinfo=UTC)
    previous = DashboardPayload(
        generated_at=timestamp,
        sources={
            "yahoo_ixic": SourceStatus(source="yahoo_ixic", available=True, checked_at=timestamp)
        },
        market={
            "qqq": {"symbol": "QQQ", "price": 500.0},
            "ixic": {"symbol": "^IXIC", "price": 18000.0, "candles": [{"time": "2026-08-03"}]},
        },
    )

    payload = build_dashboard_payload(
        generated_at=timestamp,
        sources={
            "yahoo_ixic": SourceStatus(
                source="yahoo_ixic", available=False, checked_at=timestamp, message="timeout"
            )
        },
        market={"qqq": {"symbol": "QQQ", "price": 510.0}},
        previous=previous,
    )

    assert payload.market["qqq"]["price"] == 510.0
    assert payload.market["ixic"]["price"] == 18000.0
    assert payload.sources["yahoo_ixic"].stale is True
