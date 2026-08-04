from datetime import UTC, datetime
from pathlib import Path

from app.db import SnapshotRepository
from app.models import DashboardPayload, Decision, SourceStatus
from app.scheduler import refresh_once


def status() -> SourceStatus:
    return SourceStatus(
        source="yahoo", available=True, checked_at=datetime.now(UTC)
    )


def build_payload(state: str, moment: datetime) -> DashboardPayload:
    return DashboardPayload(
        generated_at=moment,
        sources={"yahoo": status()},
        decision=Decision(
            state=state,
            allocation_min=40,
            allocation_max=40,
            target_allocation=40.0,
            dca_multiplier=1.0,
            reasons=[f"原因-{state}"],
            non_triggers=[],
            actionability="按常规定投",
        ),
    )


def test_refresh_once_attaches_state_history(
    tmp_path: Path,
) -> None:
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite3")
    export_path = tmp_path / "dashboard.json"

    def collect(previous):
        moment = datetime(2026, 8, 3, 10, 0, tzinfo=UTC)
        repository.record_state(build_payload("neutral", moment))
        return build_payload("constructive", datetime(2026, 8, 3, 10, 15, tzinfo=UTC))

    payload = refresh_once(repository, export_path, collect=collect)

    assert payload.state_history is not None
    assert payload.state_history["current_duration_ticks"] == 1
    states = [item["state"] for item in payload.state_history["switches"]]
    assert states == ["neutral", "constructive"]


def test_refresh_once_state_history_none_without_decision(
    tmp_path: Path,
) -> None:
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite3")
    export_path = tmp_path / "dashboard.json"

    def collect(previous):
        payload = build_payload("neutral", datetime(2026, 8, 3, 10, 0, tzinfo=UTC))
        return payload.model_copy(update={"decision": None})

    payload = refresh_once(repository, export_path, collect=collect)

    assert payload.decision is None
    assert payload.state_history is None
