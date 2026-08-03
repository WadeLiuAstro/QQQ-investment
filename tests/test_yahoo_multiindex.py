import pandas as pd

from app.providers.yahoo import fetch_daily_bars


def test_yahoo_multiindex_response_maps_one_symbol_to_price_bar() -> None:
    columns = pd.MultiIndex.from_tuples([("Close", "QQQ"), ("Volume", "QQQ")])
    frame = pd.DataFrame([[682.12, 12_345_678]], columns=columns, index=pd.to_datetime(["2026-07-27"]))

    bars, status = fetch_daily_bars("QQQ", "5d", downloader=lambda *_args, **_kwargs: frame)

    assert status.available is True
    assert bars[0].close == 682.12
    assert bars[0].volume == 12_345_678
