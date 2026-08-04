"""S2a: 大跌检测与证据集组装测试（体系 §5）。"""

from datetime import UTC, date, datetime, timedelta

from app.models import MacroEvent
from app.providers.yahoo import PriceBar
from app.services.attribution import build_evidence_set


def bars(closes: list[float]) -> list[PriceBar]:
    start = date(2025, 1, 1)
    return [
        PriceBar(day=start + timedelta(days=index), close=close, volume=1_000_000)
        for index, close in enumerate(closes)
    ]


def test_no_crash_on_normal_day() -> None:
    evidence = build_evidence_set(bars([100.0, 100.5, 101.0, 100.8, 101.2]))
    assert evidence.available
    assert evidence.triggered is False


def test_daily_drop_of_two_percent_triggers() -> None:
    evidence = build_evidence_set(bars([100.0, 100.5, 101.0, 99.5, 97.0]))
    assert evidence.triggered is True
    assert evidence.daily_change_pct is not None
    assert evidence.daily_change_pct <= -2.0


def test_new_drawdown_tier_triggers_without_single_day_drop() -> None:
    # 高点 110，缓慢跌至 94（-14.5%），再跌至 91.5（-16.8%）→ 跨越 -15% 档
    closes = [100.0] * 240 + [110.0] + [100.0, 98.0, 96.0, 95.0, 94.0, 91.5]
    evidence = build_evidence_set(bars(closes))
    assert evidence.triggered is True
    assert evidence.drawdown_pct is not None
    assert evidence.drawdown_pct <= -15.0


def test_shallow_drawdown_does_not_cross_tier() -> None:
    closes = [100.0] * 240 + [110.0] + [105.0, 102.0, 100.0, 99.0, 98.0]
    evidence = build_evidence_set(bars(closes))
    assert evidence.triggered is False


def test_evidence_includes_vix_and_spike() -> None:
    qqq = bars([100.0, 100.5, 101.0, 99.5, 97.0])
    vix = bars([15.0, 16.0, 17.0, 18.0, 22.0, 30.0])
    evidence = build_evidence_set(qqq, vix_bars=vix)
    assert evidence.vix == 30.0
    assert evidence.vix_spike_pct is not None
    assert evidence.vix_spike_pct >= 50.0  # 5 日跳升 100%


def test_evidence_includes_breadth_rs() -> None:
    qqq = bars([100.0] * 16 + [100.5, 101.0, 99.5, 97.0, 95.0])  # 21 根，20 日 -5%
    qqqe = bars([100.0] * 16 + [99.0, 98.0, 96.0, 94.0, 92.0])  # 21 根，20 日 -8%
    evidence = build_evidence_set(qqq, qqqe_bars=qqqe)
    # QQQE 跑输 QQQ → RS 为负
    assert evidence.rs_20d is not None and evidence.rs_20d < 0
    assert evidence.rs_5d is not None and evidence.rs_5d < 0


def test_evidence_includes_pending_events() -> None:
    today = date(2026, 8, 4)
    events = [
        MacroEvent(kind="FOMC", title="FOMC 会议", event_at=datetime(2026, 8, 6, 18, 0), source="test"),
        MacroEvent(kind="CPI", title="CPI 数据", event_at=datetime(2026, 8, 12, 12, 30), source="test"),
    ]
    qqq = bars([100.0, 100.5, 101.0, 99.5, 97.0])
    evidence = build_evidence_set(qqq, events=events, today=today)
    assert "FOMC 会议" in evidence.pending_events
    assert "CPI 数据" not in evidence.pending_events


def test_insufficient_data_unavailable() -> None:
    evidence = build_evidence_set(bars([100.0]))
    assert evidence.available is False
    assert evidence.triggered is False
