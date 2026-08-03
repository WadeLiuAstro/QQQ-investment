from datetime import UTC, datetime
from pathlib import Path

from app.models import DashboardPayload, SourceStatus
from app.services.export import write_dashboard_json


def test_export_replaces_json_atomically(tmp_path: Path) -> None:
    timestamp = datetime(2026, 8, 3, tzinfo=UTC)
    payload = DashboardPayload(
        generated_at=timestamp,
        sources={
            "yahoo": SourceStatus(source="yahoo", available=True, checked_at=timestamp)
        },
        market={"qqq": {"symbol": "QQQ", "price": 500.0}},
    )
    destination = tmp_path / "dashboard.json"

    write_dashboard_json(payload, destination)

    assert DashboardPayload.model_validate_json(destination.read_text()).generated_at == timestamp
    assert not list(tmp_path.glob("*.tmp"))
