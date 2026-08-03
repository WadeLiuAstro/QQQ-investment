import sqlite3
from pathlib import Path

from app.models import DashboardPayload, SourceStatus


class SnapshotRepository:
    def __init__(self, db_path: Path) -> None:
        self._connection = sqlite3.connect(db_path)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS payload_snapshots (
                generated_at TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS source_health (
                source TEXT PRIMARY KEY,
                checked_at TEXT NOT NULL,
                status_json TEXT NOT NULL
            )
            """
        )

    def save_payload(self, payload: DashboardPayload) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO payload_snapshots(generated_at, payload_json) VALUES (?, ?)",
            (payload.generated_at.isoformat(), payload.model_dump_json()),
        )
        self._connection.commit()

    def load_latest_payload(self) -> DashboardPayload | None:
        row = self._connection.execute(
            "SELECT payload_json FROM payload_snapshots ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
        return DashboardPayload.model_validate_json(row[0]) if row else None

    def record_source_status(self, status: SourceStatus) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO source_health(source, checked_at, status_json) VALUES (?, ?, ?)",
            (status.source, status.checked_at.isoformat(), status.model_dump_json()),
        )
        self._connection.commit()

    def load_source_status(self, source: str) -> SourceStatus | None:
        row = self._connection.execute(
            "SELECT status_json FROM source_health WHERE source = ?", (source,)
        ).fetchone()
        return SourceStatus.model_validate_json(row[0]) if row else None