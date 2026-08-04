from datetime import datetime, date
from zoneinfo import ZoneInfo

import pytest

from app.providers.yahoo import fetch_quote
from app.services.session import (
    expected_bar_date,
    is_regular_session_open,
    latest_trading_day,
    session_elapsed_fraction,
    trading_day_lag,
)

NY = ZoneInfo("America/New_York")


class Ticker:
    fast_info = {"last_price": 510.25, "previous_close": 505.0}


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 8, 4, 9, 29, tzinfo=NY), False),
        (datetime(2026, 8, 4, 9, 30, tzinfo=NY), True),
        (datetime(2026, 8, 4, 15, 59, tzinfo=NY), True),
        (datetime(2026, 8, 4, 16, 0, tzinfo=NY), False),
        (datetime(2026, 8, 1, 12, 0, tzinfo=NY), False),  # Saturday
        (datetime(2026, 8, 2, 12, 0, tzinfo=NY), False),  # Sunday
    ],
)
def test_is_regular_session_open_boundaries(moment: datetime, expected: bool) -> None:
    assert is_regular_session_open(moment) is expected


def test_session_open_accepts_utc_input() -> None:
    # 2026-08-04 18:00 UTC == 14:00 New York (session open)
    assert is_regular_session_open(datetime(2026, 8, 4, 18, 0, tzinfo=ZoneInfo("UTC"))) is True


def test_session_elapsed_fraction_values() -> None:
    assert session_elapsed_fraction(datetime(2026, 8, 4, 9, 30, tzinfo=NY)) == pytest.approx(0.0)
    assert session_elapsed_fraction(datetime(2026, 8, 4, 13, 0, tzinfo=NY)) == pytest.approx(210 / 390)
    assert session_elapsed_fraction(datetime(2026, 8, 4, 16, 0, tzinfo=NY)) == pytest.approx(1.0)
    assert session_elapsed_fraction(datetime(2026, 8, 4, 20, 0, tzinfo=NY)) is None
    assert session_elapsed_fraction(datetime(2026, 8, 1, 13, 0, tzinfo=NY)) is None


def test_fetch_quote_market_open_flag_explicit() -> None:
    open_quote, _ = fetch_quote("QQQ", ticker_factory=lambda _: Ticker(), market_open=True)
    closed_quote, _ = fetch_quote("QQQ", ticker_factory=lambda _: Ticker(), market_open=False)
    assert open_quote.is_intraday_estimate is True
    assert closed_quote.is_intraday_estimate is False


def test_fetch_quote_default_flag_computed_from_session(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.providers.yahoo as yahoo

    calls: list[bool] = []

    def fake_session_open(now=None) -> bool:
        calls.append(True)
        return False

    monkeypatch.setattr(yahoo, "is_regular_session_open", fake_session_open)
    quote, _ = fetch_quote("QQQ", ticker_factory=lambda _: Ticker())
    assert quote.is_intraday_estimate is False
    assert calls == [True]


def test_latest_trading_day_skips_weekends() -> None:
    assert latest_trading_day(date(2026, 8, 5)) == date(2026, 8, 5)  # Wednesday
    assert latest_trading_day(date(2026, 8, 8)) == date(2026, 8, 7)  # Saturday -> Friday
    assert latest_trading_day(date(2026, 8, 9)) == date(2026, 8, 7)  # Sunday -> Friday


def test_trading_day_lag_counts_weekdays_only() -> None:
    # 周一收盘价数据在周三检查：滞后 2 个交易日（周二、周三）
    assert trading_day_lag(date(2026, 8, 3), date(2026, 8, 5)) == 2
    # 同日：滞后 0
    assert trading_day_lag(date(2026, 8, 3), date(2026, 8, 3)) == 0
    # 周五数据在周一检查：滞后 1 个交易日（周一）
    assert trading_day_lag(date(2026, 8, 7), date(2026, 8, 10)) == 1
    # 未来日期（不应出现）：滞后 0
    assert trading_day_lag(date(2026, 8, 10), date(2026, 8, 7)) == 0


def test_expected_bar_date_uses_last_closed_trading_day() -> None:
    # 周一盘前 02:00：最近已收盘交易日是上周五
    assert expected_bar_date(datetime(2026, 8, 3, 2, 0, tzinfo=NY)) == date(2026, 7, 31)
    # 周一 17:00（已收盘）：当天算最近已收盘交易日
    assert expected_bar_date(datetime(2026, 8, 3, 17, 0, tzinfo=NY)) == date(2026, 8, 3)
    # 周六：回退到周五
    assert expected_bar_date(datetime(2026, 8, 8, 12, 0, tzinfo=NY)) == date(2026, 8, 7)
    # 盘中 13:00：当天尚未收盘，最近已收盘是前一天
    assert expected_bar_date(datetime(2026, 8, 4, 13, 0, tzinfo=NY)) == date(2026, 8, 3)
