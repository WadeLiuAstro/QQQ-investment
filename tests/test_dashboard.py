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
