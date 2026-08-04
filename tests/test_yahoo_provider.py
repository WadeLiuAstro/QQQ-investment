from app.providers.yahoo import fetch_daily_bars, fetch_quote


class Ticker:
    fast_info = {"last_price": 510.25, "previous_close": 505.0}


def test_yahoo_download_failure_returns_unavailable_status() -> None:
    def failing_download(**_: object) -> object:
        raise RuntimeError("provider unavailable")

    bars, status = fetch_daily_bars("QQQ", "1y", downloader=failing_download, sleeper=lambda _s: None)

    assert bars is None
    assert status.available is False
    assert status.source == "yahoo"

def test_yahoo_download_requests_unadjusted_closes() -> None:
    captured: dict[str, object] = {}

    def downloader(*_: object, **kwargs: object) -> object:
        captured.update(kwargs)
        raise RuntimeError("stop after request inspection")

    fetch_daily_bars("QQQ", "1y", downloader=downloader, sleeper=lambda _s: None)

    assert captured["auto_adjust"] is False


def test_yahoo_download_retries_once_on_transient_failure() -> None:
    import pandas as pd

    frame = pd.DataFrame(
        {"Close": [100.0], "Volume": [1000], "Open": [99.0], "High": [101.0], "Low": [98.0]},
        index=[pd.Timestamp("2026-08-03")],
    )
    calls = []

    def flaky(*_a: object, **_k: object) -> object:
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("transient failure")
        return frame

    bars, status = fetch_daily_bars("QQQ", "1y", downloader=flaky, sleeper=lambda _s: None)

    assert status.available is True
    assert bars is not None and len(bars) == 1
    assert len(calls) == 2


def test_yahoo_download_gives_up_after_two_attempts() -> None:
    calls = []

    def failing(*_a: object, **_k: object) -> object:
        calls.append(1)
        raise ValueError("persistent failure")

    bars, status = fetch_daily_bars("QQQ", "1y", downloader=failing, sleeper=lambda _s: None)

    assert bars is None
    assert status.available is False
    assert len(calls) == 2


def test_yahoo_quote_retries_once_on_transient_failure() -> None:
    calls = []

    def flaky_factory(_symbol: str) -> object:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("transient failure")
        return Ticker()

    quote, status = fetch_quote("QQQ", ticker_factory=flaky_factory, sleeper=lambda _s: None)

    assert status.available is True
    assert quote.price == 510.25
    assert len(calls) == 2


def test_yahoo_quote_gives_up_after_two_attempts() -> None:
    calls = []

    def failing_factory(_symbol: str) -> object:
        calls.append(1)
        raise RuntimeError("persistent failure")

    quote, status = fetch_quote("QQQ", ticker_factory=failing_factory, sleeper=lambda _s: None)

    assert quote is None
    assert status.available is False
    assert len(calls) == 2

