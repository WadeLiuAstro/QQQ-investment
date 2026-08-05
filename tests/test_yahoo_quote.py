from yfinance.exceptions import YFRateLimitError

from app.providers.yahoo import fetch_quote


def test_yahoo_quote_maps_fast_info() -> None:
    class Ticker:
        fast_info = {"last_price": 510.25, "previous_close": 505.0}

    quote, status = fetch_quote("QQQ", ticker_factory=lambda _: Ticker(), market_open=True)

    assert status.available is True
    assert quote.symbol == "QQQ"
    assert quote.price == 510.25
    assert quote.previous_close == 505.0
    assert quote.is_intraday_estimate is True


def test_yahoo_quote_failure_returns_unavailable_status() -> None:
    def failing_factory(_: str) -> object:
        raise RuntimeError("quote provider unavailable")

    quote, status = fetch_quote("QQQ", ticker_factory=failing_factory, sleeper=lambda _s: None)

    assert quote is None
    assert status.available is False


def test_yahoo_quote_rate_limit_degrades_gracefully() -> None:
    """已复现：Yahoo 限流抛 YFRateLimitError，必须降级为不可用而非崩溃。"""

    class RateLimitedTicker:
        @property
        def fast_info(self) -> object:
            raise YFRateLimitError()

    quote, status = fetch_quote(
        "QQQ", ticker_factory=lambda _: RateLimitedTicker(), sleeper=lambda _s: None
    )

    assert quote is None
    assert status.available is False
