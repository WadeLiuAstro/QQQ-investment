"""S2c: 归因闸门状态机测试（体系 §5：拍板三分类 + 超时减半）。"""

from datetime import UTC, datetime, timedelta

from app.services.attribution import CrashEvidence, evaluate_attribution_gate


def _evidence(triggered: bool) -> CrashEvidence:
    return CrashEvidence(available=True, triggered=triggered)


def test_gate_open_when_no_crash() -> None:
    gate = evaluate_attribution_gate(_evidence(False))
    assert gate.status == "open"


def test_gate_half_when_pending_no_decision() -> None:
    now = datetime.now(UTC)
    gate = evaluate_attribution_gate(_evidence(True), now=now)
    assert gate.status == "half"
    assert gate.pending is True
    assert gate.deadline is not None
    assert gate.deadline - now >= timedelta(hours=47)  # 48 小时倒计时


def test_gate_open_after_liquidity_panic_decision() -> None:
    decision = {
        "classification": "liquidity_panic",
        "reason": "VIX 跳升但宽度未恶化",
        "decided_at": datetime.now(UTC).isoformat(),
    }
    gate = evaluate_attribution_gate(_evidence(True), decision=decision)
    assert gate.status == "open"
    assert gate.pending is False


def test_gate_frozen_after_structural_decision() -> None:
    decision = {
        "classification": "structural",
        "reason": "确认结构性风险",
        "decided_at": datetime.now(UTC).isoformat(),
    }
    gate = evaluate_attribution_gate(_evidence(True), decision=decision)
    assert gate.status == "frozen"


def test_gate_half_with_review_deadline_after_watch_decision() -> None:
    decided_at = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    decision = {
        "classification": "watch",
        "reason": "证据不足先观察",
        "decided_at": decided_at.isoformat(),
        "expires_at": (decided_at + timedelta(hours=48)).isoformat(),
    }
    gate = evaluate_attribution_gate(_evidence(True), decision=decision)
    assert gate.status == "half"
    assert gate.pending is False
    assert gate.deadline is not None
    assert gate.deadline == decided_at + timedelta(hours=48)
