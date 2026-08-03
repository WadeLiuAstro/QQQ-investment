from pathlib import Path

from fastapi.testclient import TestClient

from app.db import SnapshotRepository
from app.main import create_app


def test_api_starts_and_stops_refresh_scheduler_with_its_lifecycle(tmp_path: Path) -> None:
    app = create_app(SnapshotRepository(tmp_path / "dashboard.sqlite"), tmp_path / "dashboard.json")

    with TestClient(app):
        assert app.state.refresh_scheduler.running is True

    assert app.state.refresh_scheduler.running is False
