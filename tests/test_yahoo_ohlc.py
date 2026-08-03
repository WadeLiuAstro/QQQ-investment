import pandas as pd

from app.providers.yahoo import fetch_daily_bars


def test_yahoo_daily_bars_include_ohlc_when_response_provides_it() -> None:
    frame = pd.DataFrame(
        [[100.0, 105.0, 98.0, 102.0, 1_000]],
        columns=["Open", "High", "Low", "Close", "Volume"],
        index=pd.to_datetime(["2026-08-03"]),
    )

    bars, status = fetch_daily_bars(
        "^IXIC", "1y", downloader=lambda *_args, **_kwargs: frame
    )

    assert status.available is True
    assert bars is not None
    assert (bars[0].open, bars[0].high, bars[0].low, bars[0].close) == (
        100.0,
        105.0,
        98.0,
        102.0,
    )
