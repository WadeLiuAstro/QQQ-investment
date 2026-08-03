from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import SnapshotRepository
from app.main import create_app
from app.models import DashboardPayload, SourceStatus
from app.services.export import write_dashboard_json


def test_dashboard_api_recovers_from_static_snapshot_when_database_is_empty(
    tmp_path: Path,
) -> None:
    timestamp = datetime(2026, 8, 3, tzinfo=UTC)
    payload = DashboardPayload(
        generated_at=timestamp,
        sources={
            "yahoo": SourceStatus(source="yahoo", available=True, checked_at=timestamp)
        },
        market={"qqq": {"symbol": "QQQ", "price": 500.0}},
    )
    export_path = tmp_path / "dashboard.json"
    write_dashboard_json(payload, export_path)
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite")

    response = TestClient(create_app(repository, export_path)).get("/api/dashboard")

    assert response.status_code == 200
    assert response.json()["market"]["qqq"]["price"] == 500.0
    assert repository.load_latest_payload() == payload
