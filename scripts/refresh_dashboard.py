from pathlib import Path

from app.config import PROJECT_ROOT
from app.db import SnapshotRepository
from app.scheduler import refresh_once


if __name__ == "__main__":
    repository = SnapshotRepository(PROJECT_ROOT / "data" / "dashboard.sqlite")
    refresh_once(repository, PROJECT_ROOT / "static" / "data" / "dashboard.json")
