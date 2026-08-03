from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Callable

import yfinance as yf

from app.models import SourceStatus


@dataclass(frozen=True)
class PriceBar:
    day: date
    close: float
    volume: int


def fetch_daily_bars(
    symbol: str,
    period: str,
    downloader: Callable[..., object] = yf.download,
) -> tuple[list[PriceBar] | None, SourceStatus]:
    checked_at = datetime.now(UTC)
    try:
        frame = downloader(symbol, period=period, interval="1d", progress=False, auto_adjust=False)
        if frame.empty:
            raise ValueError("empty market-data response")
        if getattr(frame.columns, "nlevels", 1) > 1:
            frame = frame.xs(symbol, axis=1, level=-1)
        bars = [
            PriceBar(day=index.date(), close=float(row["Close"]), volume=int(row["Volume"]))
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

