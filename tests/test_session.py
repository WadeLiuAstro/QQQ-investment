from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.providers.yahoo import fetch_quote
from app.services.session import is_regular_session_open, session_elapsed_fraction

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
