from datetime import date

from app.providers.yahoo import PriceBar
from app.scheduler import _market_card


def test_ixic_market_card_exports_candles_and_daily_change() -> None:
    card = _market_card(
        "^IXIC",
        [
            PriceBar(date(2026, 8, 2), 100.0, 1_000, 99.0, 101.0, 98.0),
            PriceBar(date(2026, 8, 3), 102.0, 1_000, 100.0, 105.0, 99.0),
        ],
    )

    assert card["daily_change_points"] == 2.0
    assert card["daily_change_pct"] == 2.0
    assert card["candles"] == [
        {"time": "2026-08-02", "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        {"time": "2026-08-03", "open": 100.0, "high": 105.0, "low": 99.0, "close": 102.0},
    ]
