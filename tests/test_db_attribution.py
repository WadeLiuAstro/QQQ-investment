"""S2b: 归因拍板与决策日志持久化测试。"""

from datetime import UTC, datetime
from pathlib import Path

from app.db import SnapshotRepository


def test_save_and_load_attribution_decision(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "test.sqlite")
    decided_at = datetime.now(UTC)

    repo.save_attribution_decision(
        incident_key="2026-08-04",
        classification="liquidity_panic",
        reason="VIX 跳升但宽度未恶化，属流动性恐慌",
        decided_at=decided_at,
    )

    decision = repo.load_attribution_decision("2026-08-04")
    assert decision is not None
    assert decision["classification"] == "liquidity_panic"
    assert "流动性恐慌" in decision["reason"]


def test_attribution_decision_upsert_overwrites(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "test.sqlite")
    now = datetime.now(UTC)

    repo.save_attribution_decision("k1", "watch", "证据不足，先观察", now)
    repo.save_attribution_decision("k1", "structural", "确认结构性风险", now)

    decisions = repo.load_attribution_decisions()
    assert len(decisions) == 1
    assert decisions[0]["classification"] == "structural"


def test_attribution_decisions_empty_on_new_db(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "test.sqlite")
    assert repo.load_attribution_decisions() == []


def test_append_and_load_decision_log(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "test.sqlite")

    repo.append_decision_log(category="signal", content={"kind": "trend_bear", "regime": "bear"})
    repo.append_decision_log(
        category="attribution",
        incident_key="2026-08-04",
        content={"classification": "liquidity_panic"},
    )
    repo.append_decision_log(category="execution", content={"action": "add_5pct"})

    entries = repo.load_decision_log()
    assert [entry["category"] for entry in entries] == ["signal", "attribution", "execution"]
    assert entries[1]["incident_key"] == "2026-08-04"
    assert entries[1]["content"]["classification"] == "liquidity_panic"


def test_decision_log_limit_and_order(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "test.sqlite")
    for index in range(5):
        repo.append_decision_log(category="signal", content={"index": index})

    entries = repo.load_decision_log(limit=3)
    assert len(entries) == 3
    assert [entry["content"]["index"] for entry in entries] == [2, 3, 4]


def test_decision_log_empty_on_new_db(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "test.sqlite")
    assert repo.load_decision_log() == []
