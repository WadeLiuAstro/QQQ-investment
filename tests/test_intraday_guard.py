"""盘中熔断守护服务测试：阈值触发、优雅降级与快照语义字段。"""

from datetime import date, datetime

import pytest

from app.models import DashboardPayload, IntradayWatch
from app.providers.yahoo import Quote
from app.services.intraday_guard import (
    QQQ_DROP_THRESHOLD_PCT,
    VIX_ABSOLUTE_THRESHOLD,
    VIX_SPIKE_CHANGE_PCT,
    GuardFinding,
    build_circuit_alerts,
    detect_circuit_events,
)


def _quote(symbol: str, price: float, previous_close: float) -> Quote:
    return Quote(
        symbol=symbol,
        price=price,
        previous_close=previous_close,
        is_intraday_estimate=False,
    )


class TestConstants:
    def test_constants_locked(self) -> None:
        assert QQQ_DROP_THRESHOLD_PCT == -3.0
        assert VIX_SPIKE_CHANGE_PCT == 20.0
        assert VIX_ABSOLUTE_THRESHOLD == 35.0


class TestDetectQqqDrop:
    def test_qqq_drop_exactly_at_threshold_triggers(self) -> None:
        findings = detect_circuit_events(_quote("QQQ", 97.0, 100.0), None)
        assert [f.kind for f in findings] == ["qqq_drop"]
        assert findings[0].metric == pytest.approx(-3.0)
        assert findings[0].threshold == QQQ_DROP_THRESHOLD_PCT
        assert "QQQ 单日下跌 3.0%" == findings[0].detail

    def test_qqq_drop_below_threshold_not_triggered(self) -> None:
        findings = detect_circuit_events(_quote("QQQ", 97.1, 100.0), None)
        assert findings == []

    def test_qqq_rise_not_triggered(self) -> None:
        findings = detect_circuit_events(_quote("QQQ", 102.0, 100.0), None)
        assert findings == []


class TestDetectVixSpike:
    def test_vix_change_exactly_at_threshold_triggers(self) -> None:
        findings = detect_circuit_events(None, _quote("^VIX", 24.0, 20.0))
        assert [f.kind for f in findings] == ["vix_spike"]
        assert findings[0].metric == pytest.approx(20.0)
        assert findings[0].threshold == VIX_SPIKE_CHANGE_PCT
        assert "VIX 单日上涨 20.0%" == findings[0].detail

    def test_vix_change_below_threshold_not_triggered(self) -> None:
        findings = detect_circuit_events(None, _quote("^VIX", 23.98, 20.0))
        assert findings == []

    def test_vix_absolute_at_threshold_triggers(self) -> None:
        findings = detect_circuit_events(None, _quote("^VIX", 35.0, 34.0))
        assert [f.kind for f in findings] == ["vix_spike"]
        assert findings[0].metric == pytest.approx(35.0)
        assert findings[0].threshold == VIX_ABSOLUTE_THRESHOLD
        assert "VIX 达到 35.0" == findings[0].detail

    def test_vix_absolute_below_threshold_not_triggered(self) -> None:
        findings = detect_circuit_events(None, _quote("^VIX", 34.9, 34.0))
        assert findings == []

    def test_vix_both_paths_triggered_emits_single_finding(self) -> None:
        findings = detect_circuit_events(None, _quote("^VIX", 40.0, 20.0))
        vix_findings = [f for f in findings if f.kind == "vix_spike"]
        assert len(vix_findings) == 1


class TestGracefulDegradation:
    def test_both_quotes_none_returns_empty(self) -> None:
        assert detect_circuit_events(None, None) == []

    def test_single_quote_none_returns_empty(self) -> None:
        assert detect_circuit_events(_quote("QQQ", 90.0, 100.0), None) != []
        assert detect_circuit_events(None, _quote("^VIX", 40.0, 20.0)) != []

    def test_previous_close_zero_skipped(self) -> None:
        assert detect_circuit_events(_quote("QQQ", 90.0, 0.0), _quote("^VIX", 40.0, 0.0)) == []

    def test_previous_close_none_skipped(self) -> None:
        qqq = Quote(symbol="QQQ", price=90.0, previous_close=None, is_intraday_estimate=False)
        vix = Quote(symbol="^VIX", price=40.0, previous_close=None, is_intraday_estimate=False)
        assert detect_circuit_events(qqq, vix) == []


class TestBothQuotesCombined:
    def test_qqq_drop_and_vix_spike_together(self) -> None:
        findings = detect_circuit_events(
            _quote("QQQ", 96.0, 100.0), _quote("^VIX", 36.5, 36.0)
        )
        kinds = [f.kind for f in findings]
        assert kinds == ["qqq_drop", "vix_spike"]


class TestBuildCircuitAlerts:
    def test_alert_key_includes_day_and_kind(self) -> None:
        day = date(2026, 8, 5)
        findings = [
            GuardFinding(
                kind="qqq_drop",
                metric=-3.4,
                threshold=QQQ_DROP_THRESHOLD_PCT,
                detail="QQQ 单日下跌 3.4%",
            ),
            GuardFinding(
                kind="vix_spike",
                metric=24.0,
                threshold=VIX_SPIKE_CHANGE_PCT,
                detail="VIX 单日上涨 24.0%",
            ),
        ]
        alerts = build_circuit_alerts(findings, day)
        assert [a.key for a in alerts] == [
            "circuit_breaker:2026-08-05:qqq_drop",
            "circuit_breaker:2026-08-05:vix_spike",
        ]

    def test_alert_kind_and_titles(self) -> None:
        findings = [
            GuardFinding(
                kind="qqq_drop",
                metric=-3.4,
                threshold=QQQ_DROP_THRESHOLD_PCT,
                detail="QQQ 单日下跌 3.4%",
            ),
            GuardFinding(
                kind="vix_spike",
                metric=24.0,
                threshold=VIX_SPIKE_CHANGE_PCT,
                detail="VIX 单日上涨 24.0%",
            ),
        ]
        alerts = build_circuit_alerts(findings, date(2026, 8, 5))
        assert all(a.kind == "circuit_breaker" for a in alerts)
        assert alerts[0].title == "熔断预警：QQQ 单日大跌"
        assert alerts[1].title == "熔断预警：VIX 恐慌飙升"

    def test_alert_detail_contains_finding_detail_and_threshold(self) -> None:
        findings = [
            GuardFinding(
                kind="qqq_drop",
                metric=-3.4,
                threshold=QQQ_DROP_THRESHOLD_PCT,
                detail="QQQ 单日下跌 3.4%",
            )
        ]
        alerts = build_circuit_alerts(findings, date(2026, 8, 5))
        assert "QQQ 单日下跌 3.4%" in alerts[0].detail
        assert "-3.0" in alerts[0].detail

    def test_empty_findings_returns_empty(self) -> None:
        assert build_circuit_alerts([], date(2026, 8, 5)) == []


class TestSnapshotModels:
    def test_intraday_watch_fields(self) -> None:
        watch = IntradayWatch(
            checked_at=datetime(2026, 8, 5, 10, 0),
            qqq_price=470.5,
            qqq_change_pct=-3.4,
            vix=36.5,
            vix_change_pct=24.0,
            triggered=True,
        )
        assert watch.triggered is True
        assert watch.qqq_change_pct == pytest.approx(-3.4)

    def test_intraday_watch_nullable_metrics(self) -> None:
        watch = IntradayWatch(
            checked_at=datetime(2026, 8, 5, 10, 0),
            qqq_price=None,
            qqq_change_pct=None,
            vix=None,
            vix_change_pct=None,
            triggered=False,
        )
        assert watch.qqq_price is None

    def test_legacy_payload_without_new_fields_validates(self) -> None:
        legacy = {
            "generated_at": "2026-08-04T20:00:00Z",
            "sources": {
                "yahoo_qqq": {
                    "source": "yahoo_qqq",
                    "available": True,
                    "checked_at": "2026-08-04T20:00:00Z",
                }
            },
        }
        payload = DashboardPayload.model_validate(legacy)
        assert payload.snapshot_kind == "daily"
        assert payload.intraday_watch is None

    def test_payload_accepts_intraday_watch(self) -> None:
        payload = DashboardPayload(
            generated_at=datetime(2026, 8, 5, 14, 30),
            sources={},
            snapshot_kind="intraday",
            intraday_watch=IntradayWatch(
                checked_at=datetime(2026, 8, 5, 14, 30),
                qqq_price=470.5,
                qqq_change_pct=-3.4,
                vix=36.5,
                vix_change_pct=24.0,
                triggered=True,
            ),
        )
        assert payload.snapshot_kind == "intraday"
        assert payload.intraday_watch is not None
