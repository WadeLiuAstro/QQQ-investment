from pathlib import Path

from apscheduler.triggers.cron import CronTrigger

from app.db import SnapshotRepository
from app.scheduler import create_refresh_scheduler


def test_refresh_scheduler_registers_daily_and_intraday_jobs(tmp_path: Path) -> None:
    scheduler = create_refresh_scheduler(
        SnapshotRepository(tmp_path / "dashboard.sqlite"), tmp_path / "dashboard.json"
    )

    daily_job = scheduler.get_job("daily_refresh")
    guard_job = scheduler.get_job("intraday_guard")

    # 日频全量刷新：工作日 16:35（收盘后）的 cron job
    assert daily_job is not None
    assert isinstance(daily_job.trigger, CronTrigger)
    trigger_text = str(daily_job.trigger)
    assert "mon-fri" in trigger_text
    assert "hour='16'" in trigger_text
    assert "minute='35'" in trigger_text

    # 盘中守护：15 分钟 interval job
    assert guard_job is not None
    assert "interval[0:15:00]" in str(guard_job.trigger)

    # 旧的单一刷新 job 已移除
    assert scheduler.get_job("dashboard_refresh") is None
    scheduler.shutdown(wait=False)
