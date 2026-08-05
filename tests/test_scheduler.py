from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.db import SnapshotRepository
from app.models import DashboardPayload, Decision, SourceStatus
from app.providers.yahoo import Quote
from app.scheduler import refresh_once, run_intraday_guard
from app.services.session import NY_TZ

SESSION_NOW = datetime(2026, 8, 3, 10, 30, tzinfo=NY_TZ)      # 周一盘中
OFF_SESSION_NOW = datetime(2026, 8, 3, 20, 0, tzinfo=NY_TZ)  # 周一收盘后


def _status(source: str) -> SourceStatus:
    return SourceStatus(
        source=source, available=True, checked_at=datetime(2026, 8, 3, tzinfo=UTC)
    )


def _quote(symbol: str, price: float, previous_close: float) -> Quote:
    return Quote(
        symbol=symbol, price=price, previous_close=previous_close, is_intraday_estimate=False
    )


def _fetch_quote_stub(qqq: Quote | None, vix: Quote | None):
    def fetch(symbol, *args, **kwargs):
        quote = qqq if symbol == "QQQ" else vix
        return quote, _status(f"yahoo_{symbol.lower()}")

    return fetch


def _baseline_payload() -> DashboardPayload:
    generated_at = datetime(2026, 8, 2, 20, 35, tzinfo=UTC)
    decision = Decision(
        state="hold",
        allocation_min=0,
        allocation_max=0,
        target_allocation=0.0,
        dca_multiplier=0.0,
        reasons=["测试理由"],
        non_triggers=["测试未触发"],
        actionability="none",
    )
    return DashboardPayload(
        generated_at=generated_at,
        sources={"yahoo_qqq": _status("yahoo_qqq")},
        market={"qqq": {"symbol": "QQQ", "price": 500.0, "daily_change_pct": -0.4}},
        decision=decision,
        backtest={"cumulative_return": 0.1},
        alerts=[
            {"key": "legacy:alert", "kind": "threshold", "title": "既有预警", "detail": "d"}
        ],
        snapshot_kind="daily",
    )


def _seed_repository(tmp_path: Path) -> tuple[SnapshotRepository, Path]:
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite")
    repository.save_payload(_baseline_payload())
    return repository, tmp_path / "dashboard.json"


def test_refresh_once_exports_and_persists_collected_payload(tmp_path: Path) -> None:
    timestamp = datetime(2026, 8, 3, tzinfo=UTC)
    expected = DashboardPayload(
        generated_at=timestamp,
        sources={
            "yahoo": SourceStatus(source="yahoo", available=True, checked_at=timestamp)
        },
        market={"qqq": {"symbol": "QQQ", "price": 500.0}},
    )
    repository = SnapshotRepository(tmp_path / "dashboard.sqlite")
    export_path = tmp_path / "dashboard.json"

    payload = refresh_once(repository, export_path, collect=lambda _: expected)

    normalized = expected.model_copy(update={"alerts": []})
    assert payload == normalized
    assert payload.alerts == []
    assert repository.load_latest_payload() == normalized
    assert DashboardPayload.model_validate_json(export_path.read_text()) == normalized


def test_guard_outside_session_returns_none_without_touching_repository(tmp_path: Path) -> None:
    repository = MagicMock()
    fetch = MagicMock(side_effect=AssertionError("时段外不应抓取报价"))

    result = run_intraday_guard(
        repository, tmp_path / "dashboard.json", fetch_quote=fetch, now=OFF_SESSION_NOW
    )

    assert result is None
    repository.save_payload.assert_not_called()
    repository.record_state.assert_not_called()
    fetch.assert_not_called()


def test_guard_without_daily_snapshot_returns_none(tmp_path: Path) -> None:
    repository = MagicMock()
    repository.load_latest_payload.return_value = None

    result = run_intraday_guard(
        repository,
        tmp_path / "dashboard.json",
        fetch_quote=_fetch_quote_stub(_quote("QQQ", 482.5, 500.0), _quote("^VIX", 20.0, 19.0)),
        now=SESSION_NOW,
    )

    assert result is None
    repository.save_payload.assert_not_called()
    repository.record_state.assert_not_called()


def test_guard_appends_circuit_alert_and_preserves_official_fields(tmp_path: Path) -> None:
    repository, export_path = _seed_repository(tmp_path)
    before = repository.load_latest_payload()
    circuit_key = f"circuit_breaker:{SESSION_NOW.date().isoformat()}:qqq_drop"

    updated = run_intraday_guard(
        repository,
        export_path,
        fetch_quote=_fetch_quote_stub(_quote("QQQ", 482.5, 500.0), _quote("^VIX", 20.0, 19.0)),
        now=SESSION_NOW,
    )

    assert updated is not None
    keys = [alert["key"] for alert in updated.alerts]
    assert circuit_key in keys
    assert "legacy:alert" in keys
    assert any(alert["kind"] == "circuit_breaker" for alert in updated.alerts)
    # 正式字段（decision/market 等）序列化后与守护前逐字节一致
    excluded = {"alerts", "intraday_watch"}
    assert updated.model_dump_json(exclude=excluded) == before.model_dump_json(exclude=excluded)
    assert updated.snapshot_kind == "daily"
    assert updated.generated_at == before.generated_at
    # 导出文件同步更新
    assert DashboardPayload.model_validate_json(export_path.read_text(encoding="utf-8")) == updated


def test_guard_dedupes_alerts_within_same_trading_day(tmp_path: Path) -> None:
    repository, export_path = _seed_repository(tmp_path)
    fetch = _fetch_quote_stub(_quote("QQQ", 482.5, 500.0), _quote("^VIX", 20.0, 19.0))
    circuit_key = f"circuit_breaker:{SESSION_NOW.date().isoformat()}:qqq_drop"

    first = run_intraday_guard(repository, export_path, fetch_quote=fetch, now=SESSION_NOW)
    second = run_intraday_guard(repository, export_path, fetch_quote=fetch, now=SESSION_NOW)

    first_keys = [alert["key"] for alert in first.alerts]
    second_keys = [alert["key"] for alert in second.alerts]
    assert second_keys == first_keys
    assert second_keys.count(circuit_key) == 1


def test_guard_records_intraday_watch_fields(tmp_path: Path) -> None:
    repository, export_path = _seed_repository(tmp_path)

    updated = run_intraday_guard(
        repository,
        export_path,
        fetch_quote=_fetch_quote_stub(_quote("QQQ", 482.5, 500.0), _quote("^VIX", 20.0, 19.0)),
        now=SESSION_NOW,
    )

    watch = updated.intraday_watch
    assert watch is not None
    assert watch.triggered is True
    assert watch.qqq_price == 482.5
    assert watch.qqq_change_pct == pytest.approx(-3.5)
    assert watch.vix == 20.0
    assert watch.vix_change_pct == pytest.approx((20.0 / 19.0 - 1.0) * 100)
    assert watch.checked_at == SESSION_NOW.astimezone(UTC)


def test_guard_without_trigger_keeps_alerts_and_marks_watch_not_triggered(
    tmp_path: Path,
) -> None:
    repository, export_path = _seed_repository(tmp_path)
    before = repository.load_latest_payload()

    updated = run_intraday_guard(
        repository,
        export_path,
        fetch_quote=_fetch_quote_stub(_quote("QQQ", 495.0, 500.0), _quote("^VIX", 20.0, 19.0)),
        now=SESSION_NOW,
    )

    assert updated.intraday_watch.triggered is False
    assert not any(alert["kind"] == "circuit_breaker" for alert in updated.alerts)
    assert updated.alerts == before.alerts


def test_guard_handles_missing_quotes(tmp_path: Path) -> None:
    repository, export_path = _seed_repository(tmp_path)

    updated = run_intraday_guard(
        repository, export_path, fetch_quote=_fetch_quote_stub(None, None), now=SESSION_NOW
    )

    watch = updated.intraday_watch
    assert watch.triggered is False
    assert watch.qqq_price is None
    assert watch.qqq_change_pct is None
    assert watch.vix is None
    assert watch.vix_change_pct is None


def test_guard_persists_payload_but_does_not_record_state(tmp_path: Path) -> None:
    repository = MagicMock()
    repository.load_latest_payload.return_value = _baseline_payload()

    updated = run_intraday_guard(
        repository,
        tmp_path / "dashboard.json",
        fetch_quote=_fetch_quote_stub(_quote("QQQ", 482.5, 500.0), _quote("^VIX", 20.0, 19.0)),
        now=SESSION_NOW,
    )

    repository.save_payload.assert_called_once_with(updated)
    repository.record_state.assert_not_called()
