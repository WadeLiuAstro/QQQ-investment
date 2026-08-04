from datetime import UTC, datetime
from pathlib import Path

from app.db import SnapshotRepository
from app.models import DashboardPayload, SourceStatus
from app.scheduler import refresh_once


def test_refresh_once_exports_and_persists_collected_payload(tmp_path: Path) -> None:
    timestamp = datetime(2026, 8, 3, tzinfo=UTC)
    expected = DashboardPayload(
        generated_at=timestamp,
        sources={
            "yahoo": SourceStatus(source="yahoo", available=True, checked_at=timestamp)
        },
        market={"qqq": {"symbol": "QQQ", "price": 500.0}},
    )
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite")
    export_path = tmp_path / "dashboard.json"

    payload = refresh_once(repository, export_path, collect=lambda _: expected)

    normalized = expected.model_copy(update={"alerts": []})
    assert payload == normalized
    assert payload.alerts == []
    assert repository.load_latest_payload() == normalized
    assert DashboardPayload.model_validate_json(export_path.read_text()) == normalized
