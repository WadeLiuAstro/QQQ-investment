import json
import sqlite3
from datetime import UTC, datetime
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
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS attribution_decisions (
                incident_key TEXT PRIMARY KEY,
                classification TEXT NOT NULL,
                reason TEXT NOT NULL,
                decided_at TEXT NOT NULL,
                expires_at TEXT
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                logged_at TEXT NOT NULL,
                incident_key TEXT,
                category TEXT NOT NULL,
                content_json TEXT NOT NULL
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

    def save_attribution_decision(
        self,
        incident_key: str,
        classification: str,
        reason: str,
        decided_at: datetime,
        expires_at: datetime | None = None,
    ) -> None:
        self._connection.execute(
            """
            INSERT OR REPLACE INTO attribution_decisions(
                incident_key, classification, reason, decided_at, expires_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                incident_key,
                classification,
                reason,
                decided_at.isoformat(),
                expires_at.isoformat() if expires_at else None,
            ),
        )
        self._connection.commit()

    def load_attribution_decision(self, incident_key: str) -> dict[str, object] | None:
        row = self._connection.execute(
            "SELECT classification, reason, decided_at, expires_at "
            "FROM attribution_decisions WHERE incident_key = ?",
            (incident_key,),
        ).fetchone()
        if row is None:
            return None
        return {
            "incident_key": incident_key,
            "classification": row[0],
            "reason": row[1],
            "decided_at": row[2],
            "expires_at": row[3],
        }

    def load_attribution_decisions(self) -> list[dict[str, object]]:
        rows = self._connection.execute(
            "SELECT incident_key, classification, reason, decided_at, expires_at "
            "FROM attribution_decisions ORDER BY decided_at DESC"
        ).fetchall()
        return [
            {
                "incident_key": row[0],
                "classification": row[1],
                "reason": row[2],
                "decided_at": row[3],
                "expires_at": row[4],
            }
            for row in rows
        ]

    def append_decision_log(
        self,
        category: str,
        content: dict[str, object],
        incident_key: str | None = None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO decision_log(logged_at, incident_key, category, content_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                datetime.now(UTC).isoformat(),
                incident_key,
                category,
                json.dumps(content, ensure_ascii=False),
            ),
        )
        self._connection.commit()

    def load_decision_log(self, limit: int = 50) -> list[dict[str, object]]:
        rows = self._connection.execute(
            "SELECT logged_at, incident_key, category, content_json "
            "FROM decision_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "logged_at": row[0],
                "incident_key": row[1],
                "category": row[2],
                "content": json.loads(row[3]),
            }
            for row in reversed(rows)
        ]
