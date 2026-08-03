from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import SnapshotRepository
from app.main import create_app
from app.models import DashboardPayload, SourceStatus


def sample_payload() -> DashboardPayload:
    timestamp = datetime(2026, 8, 3, tzinfo=UTC)
    return DashboardPayload(
        generated_at=timestamp,
        sources={
            "yahoo": SourceStatus(source="yahoo", available=True, checked_at=timestamp)
        },
        market={"qqq": {"symbol": "QQQ", "price": 500.0}},
    )


def test_dashboard_api_returns_503_without_snapshot(tmp_path: Path) -> None:
    app = create_app(SnapshotRepository(tmp_path / "dashboard.sqlite"), tmp_path / "dashboard.json")

    response = TestClient(app).get("/api/dashboard")

    assert response.status_code == 503
    assert response.json()["detail"] == "No successful dashboard snapshot exists"


def test_refresh_endpoint_persists_and_returns_payload(tmp_path: Path) -> None:
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite")
    export_path = tmp_path / "dashboard.json"

    def refresh(_: SnapshotRepository, __: Path) -> DashboardPayload:
        payload = sample_payload()
        repository.save_payload(payload)
        return payload

    app = create_app(repository, export_path, refresh=refresh)
    response = TestClient(app).post("/api/refresh")

    assert response.status_code == 200
    assert response.json()["market"]["qqq"]["price"] == 500.0
    assert TestClient(app).get("/api/dashboard").status_code == 200
