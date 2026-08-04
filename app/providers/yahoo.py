from dataclasses import dataclass
from datetime import UTC, date, datetime
from time import sleep
from typing import Callable

import yfinance as yf

from app.models import SourceStatus
from app.services.session import is_regular_session_open


@dataclass(frozen=True)
class PriceBar:
    day: date
    close: float
    volume: int
    open: float | None = None
    high: float | None = None
    low: float | None = None


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: float
    previous_close: float
    is_intraday_estimate: bool


RETRYABLE = (AttributeError, KeyError, TypeError, ValueError, RuntimeError)


def _call_with_retry(
    fn: Callable[[], object],
    sleeper: Callable[[float], None] = sleep,
    attempts: int = 2,
    delay: float = 0.5,
) -> object:
    """Run fn, retrying once after a short backoff on retryable errors."""
    for index in range(attempts):
        try:
            return fn()
        except RETRYABLE:
            if index == attempts - 1:
                raise
            sleeper(delay)
    raise AssertionError("unreachable")


def fetch_daily_bars(
    symbol: str,
    period: str,
    downloader: Callable[..., object] = yf.download,
    sleeper: Callable[[float], None] = sleep,
) -> tuple[list[PriceBar] | None, SourceStatus]:
    checked_at = datetime.now(UTC)
    try:
        frame = _call_with_retry(
            lambda: downloader(symbol, period=period, interval="1d", progress=False, auto_adjust=False),
            sleeper=sleeper,
        )
        if frame.empty:
            raise ValueError("empty market-data response")
        if getattr(frame.columns, "nlevels", 1) > 1:
            frame = frame.xs(symbol, axis=1, level=-1)
        bars = [
            PriceBar(day=index.date(), close=float(row["Close"]), volume=int(row["Volume"]), open=float(row["Open"]) if "Open" in row else None, high=float(row["High"]) if "High" in row else None, low=float(row["Low"]) if "Low" in row else None)
            for index, row in frame.iterrows()
        ]
        return bars, SourceStatus(source="yahoo", available=True, checked_at=checked_at)
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as error:
        return (
            None,
            SourceStatus(
                source="yahoo",
                available=False,
                checked_at=checked_at,
                message=str(error),
            ),
        )

def fetch_quote(
    symbol: str,
    ticker_factory: Callable[[str], object] = yf.Ticker,
    market_open: bool | None = None,
    sleeper: Callable[[float], None] = sleep,
) -> tuple[Quote | None, SourceStatus]:
    checked_at = datetime.now(UTC)
    if market_open is None:
        market_open = is_regular_session_open()
    try:
        def _load() -> object:
            return ticker_factory(symbol).fast_info

        fast_info = _call_with_retry(_load, sleeper=sleeper)
        quote = Quote(
            symbol=symbol,
            price=float(fast_info["last_price"]),
            previous_close=float(fast_info["previous_close"]),
            is_intraday_estimate=market_open,
        )
        return quote, SourceStatus(source="yahoo_quote", available=True, checked_at=checked_at)
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as error:
        return (
            None,
            SourceStatus(
                source="yahoo_quote",
                available=False,
                checked_at=checked_at,
                message=str(error),
            ),
        )

