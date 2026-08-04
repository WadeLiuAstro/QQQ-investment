"""S2c: 归因拍板 API 测试。"""

from datetime import UTC, date, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import SnapshotRepository
from app.main import create_app
from app.models import DashboardPayload
from app.services.attribution import CrashEvidence


def _evidence_payload(triggered: bool = True) -> DashboardPayload:
    evidence = CrashEvidence(
        available=True,
        triggered=triggered,
        day=date(2026, 8, 4),
        daily_change_pct=-2.5,
        drawdown_pct=-6.0,
        vix=28.0,
        vix_spike_pct=40.0,
        rs_20d=-1.5,
        pending_events=["FOMC 会议"],
    )
    from dataclasses import asdict

    return DashboardPayload(
        generated_at=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
        sources={},
        market={"qqq": {"attribution": {"evidence": asdict(evidence)}}},
    )


def _client(tmp_path: Path, triggered: bool = True):
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite")
    repository.save_payload(_evidence_payload(triggered))
    app = create_app(repository, tmp_path / "dashboard.json")
    return TestClient(app), repository


def test_post_attribution_saves_decision_and_opens_gate(tmp_path: Path) -> None:
    client, repository = _client(tmp_path)

    response = client.post(
        "/api/attribution",
        json={"classification": "liquidity_panic", "reason": "VIX 跳升但宽度未恶化"},
    )

    assert response.status_code == 200
    gate = response.json()["gate"]
    assert gate["status"] == "open"
    decision = repository.load_attribution_decision("2026-08-04")
    assert decision is not None
    assert decision["classification"] == "liquidity_panic"


def test_post_attribution_structural_freezes_gate(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    response = client.post(
        "/api/attribution", json={"classification": "structural", "reason": "确认结构性"}
    )

    assert response.status_code == 200
    assert response.json()["gate"]["status"] == "frozen"


def test_post_attribution_watch_sets_review_deadline(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    response = client.post(
        "/api/attribution", json={"classification": "watch", "reason": "证据不足先观察"}
    )

    assert response.status_code == 200
    gate = response.json()["gate"]
    assert gate["status"] == "half"
    assert gate["deadline"] is not None


def test_post_attribution_rejects_unknown_classification(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    response = client.post(
        "/api/attribution", json={"classification": "panic", "reason": "非法分类"}
    )

    assert response.status_code == 422


def test_post_attribution_requires_evidence_in_payload(tmp_path: Path) -> None:
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite")
    repository.save_payload(
        DashboardPayload(
            generated_at=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
            sources={},
            market={"qqq": {"price": 500.0}},
        )
    )
    app = create_app(repository, tmp_path / "dashboard.json")
    response = TestClient(app).post(
        "/api/attribution", json={"classification": "watch", "reason": "无证据"}
    )

    assert response.status_code == 400


def test_get_attribution_returns_gate_and_decision(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    client.post(
        "/api/attribution", json={"classification": "watch", "reason": "证据不足先观察"}
    )

    response = client.get("/api/attribution")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["gate"]["status"] == "half"
    assert body["decision"]["classification"] == "watch"
    assert body["evidence"]["daily_change_pct"] == -2.5


def test_get_attribution_pending_when_no_decision(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    response = client.get("/api/attribution")

    assert response.status_code == 200
    assert response.json()["gate"]["status"] == "half"
    assert response.json()["gate"]["pending"] is True


def test_decision_log_records_attribution_and_signal(tmp_path: Path) -> None:
    client, repository = _client(tmp_path)
    client.post(
        "/api/attribution", json={"classification": "watch", "reason": "证据不足先观察"}
    )

    response = client.get("/api/decision-log")

    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) >= 1
    assert any(entry["category"] == "attribution" for entry in entries)

    # 刷新流程（attach_attribution_gate）会在无拍板时写 signal 日志：模拟一次刷新前状态
    from app.scheduler import attach_attribution_gate

    repository2 = SnapshotRepository(tmp_path / "dashboard2.sqlite")
    repository2.save_payload(_evidence_payload(triggered=True))
    payload = repository2.load_latest_payload()
    assert payload is not None
    attach_attribution_gate(payload, repository2)
    entries = repository2.load_decision_log()
    assert any(entry["category"] == "signal" for entry in entries)
