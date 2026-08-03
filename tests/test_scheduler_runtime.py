from pathlib import Path

from app.db import SnapshotRepository
from app.scheduler import create_refresh_scheduler


def test_refresh_scheduler_registers_a_fifteen_minute_job(tmp_path: Path) -> None:
    scheduler = create_refresh_scheduler(
        SnapshotRepository(tmp_path / "dashboard.sqlite"), tmp_path / "dashboard.json"
    )

    job = scheduler.get_job("dashboard_refresh")

    assert job is not None
    assert "interval[0:15:00]" in str(job.trigger)
    scheduler.shutdown(wait=False)
