from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.db import SnapshotRepository
from app.models import DashboardPayload, Decision, SourceStatus


def build_payload(generated_at: datetime) -> DashboardPayload:
    return DashboardPayload(
        generated_at=generated_at,
        sources={
            "yahoo": SourceStatus(
                source="yahoo",
                available=True,
                checked_at=generated_at,
            )
        },
        decision=Decision(
            state="neutral",
            allocation_min=40,
            allocation_max=40,
            target_allocation=40.0,
            dca_multiplier=1.0,
            reasons=["趋势中性"],
            non_triggers=[],
            actionability="按常规定投",
        ),
    )


def test_repository_returns_latest_complete_payload(tmp_path: Path) -> None:
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite3")
    first = build_payload(datetime(2026, 8, 3, 10, 0, tzinfo=UTC))
    latest = build_payload(datetime(2026, 8, 3, 10, 15, tzinfo=UTC))

    repository.save_payload(first)
    repository.save_payload(latest)

    assert repository.load_latest_payload().generated_at == latest.generated_at


def test_repository_records_latest_source_status(tmp_path: Path) -> None:
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite3")
    status = SourceStatus(
        source="cnn_fear_greed",
        available=False,
        checked_at=datetime(2026, 8, 3, 10, 0, tzinfo=UTC),
        message="timeout",
    )

    repository.record_source_status(status)

    assert repository.load_source_status("cnn_fear_greed") == status


def test_repository_records_and_loads_state_history(tmp_path: Path) -> None:
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite3")
    moment = datetime(2026, 8, 3, 10, 0, tzinfo=UTC)

    repository.record_state(build_payload(moment))
    repository.record_state(
        build_payload(moment + timedelta(minutes=15)).model_copy(
            update={"generated_at": moment + timedelta(minutes=15)}
        )
    )

    records = repository.load_state_history()

    assert len(records) == 2
    assert records[0].state == "neutral"
    assert records[0].generated_at == moment
    assert records[0].allocation_min == 40
    assert records[0].dca_multiplier == 1.0
    assert records[0].reasons == ["趋势中性"]


def test_repository_skips_state_record_without_decision(tmp_path: Path) -> None:
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite3")
    payload = build_payload(datetime(2026, 8, 3, 10, 0, tzinfo=UTC))
    payload = payload.model_copy(update={"decision": None})

    repository.record_state(payload)

    assert repository.load_state_history() == []


def test_repository_loads_state_history_within_window(tmp_path: Path) -> None:
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite3")
    old = build_payload(datetime(2026, 4, 1, 10, 0, tzinfo=UTC))
    recent = build_payload(datetime(2026, 8, 3, 10, 0, tzinfo=UTC))
    repository.record_state(old)
    repository.record_state(recent)

    since = (datetime(2026, 8, 1, 0, 0, tzinfo=UTC)).isoformat()
    records = repository.load_state_history(since_iso=since)

    assert len(records) == 1
    assert records[0].generated_at == recent.generated_at