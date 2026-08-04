import json
import sqlite3
from pathlib import Path

from app.models import DashboardPayload, SourceStatus, StateRecord


class SnapshotRepository:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(db_path, check_same_thread=False)
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
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS state_history (
                generated_at TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                allocation_min INTEGER NOT NULL,
                allocation_max INTEGER NOT NULL,
                dca_multiplier REAL NOT NULL,
                reasons_json TEXT NOT NULL
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

    def record_state(self, payload: DashboardPayload) -> None:
        if payload.decision is None:
            return
        decision = payload.decision
        self._connection.execute(
            """
            INSERT OR REPLACE INTO state_history(
                generated_at, state, allocation_min, allocation_max, dca_multiplier, reasons_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload.generated_at.isoformat(),
                decision.state,
                decision.allocation_min,
                decision.allocation_max,
                decision.dca_multiplier,
                json.dumps(decision.reasons, ensure_ascii=False),
            ),
        )
        self._connection.commit()

    def load_state_history(self, since_iso: str | None = None) -> list[StateRecord]:
        query = (
            "SELECT generated_at, state, allocation_min, allocation_max, dca_multiplier, reasons_json "
            "FROM state_history"
        )
        parameters: tuple[str, ...] = ()
        if since_iso is not None:
            query += " WHERE generated_at >= ?"
            parameters = (since_iso,)
        query += " ORDER BY generated_at ASC"
        rows = self._connection.execute(query, parameters).fetchall()
        return [
            StateRecord(
                generated_at=row[0],
                state=row[1],
                allocation_min=row[2],
                allocation_max=row[3],
                dca_multiplier=row[4],
                reasons=json.loads(row[5]),
            )
            for row in rows
        ]
