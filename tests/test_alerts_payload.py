from datetime import UTC, datetime
from pathlib import Path

from app.db import SnapshotRepository
from app.models import DashboardPayload, Decision, SourceStatus
from app.scheduler import refresh_once
from app.services.alerts import build_alerts


def source(name: str, available: bool = True) -> SourceStatus:
    return SourceStatus(source=name, available=available, checked_at=datetime.now(UTC))


def build_payload(state: str | None, cnn_available: bool = True) -> DashboardPayload:
    return DashboardPayload(
        generated_at=datetime.now(UTC),
        sources={
            "yahoo_qqq": source("yahoo_qqq"),
            "cnn_fear_greed": source("cnn_fear_greed", cnn_available),
        },
        decision=(
            Decision(
                state=state,
                allocation_min=40,
                allocation_max=40,
                target_allocation=40.0,
                dca_multiplier=1.0,
                reasons=[f"原因-{state}"],
                non_triggers=[],
                actionability="",
            )
            if state
            else None
        ),
    )


def run_refresh(repository, export_path, payload) -> DashboardPayload:
    return refresh_once(repository, export_path, collect=lambda previous: payload)


def test_alerts_attached_on_state_switch(tmp_path: Path) -> None:
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite3")
    export_path = tmp_path / "dashboard.json"

    first = run_refresh(repository, export_path, build_payload("neutral"))
    second = run_refresh(repository, export_path, build_payload("constructive"))

    assert first.alerts == []
    assert second.alerts is not None
    expected = build_alerts(first, second)
    assert [a["key"] for a in second.alerts] == [a.key for a in expected]
    assert [a["key"] for a in second.alerts] == ["state_switch:constructive"]


def test_alerts_empty_when_nothing_changed(tmp_path: Path) -> None:
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite3")
    export_path = tmp_path / "dashboard.json"

    run_refresh(repository, export_path, build_payload("neutral"))
    second = run_refresh(repository, export_path, build_payload("neutral"))

    assert second.alerts == []


def test_source_stale_alert_fires_without_decision(tmp_path: Path) -> None:
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite3")
    export_path = tmp_path / "dashboard.json"

    run_refresh(repository, export_path, build_payload(None, cnn_available=False))
    second = run_refresh(repository, export_path, build_payload(None, cnn_available=False))

    assert second.decision is None
    assert [a["key"] for a in second.alerts] == ["source:cnn_fear_greed"]
