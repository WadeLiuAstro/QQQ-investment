from dataclasses import dataclass
from datetime import UTC, date, datetime
from math import isfinite
from time import sleep
from typing import Callable

import httpx
import pandas as pd
from yfinance.exceptions import YFRateLimitError

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


# yfinance 0.2.66 强制使用 curl_cffi 模拟 Chrome，其 TLS 指纹会被 Yahoo WAF
# 拦截（返回 403 验证页），导致 cookie/crumb 流程失败并误报限流；
# 普通 httpx 携带浏览器头直连 chart API 反而稳定返回 200，故改用直连实现。
_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

RETRYABLE = (
    AttributeError,
    KeyError,
    TypeError,
    ValueError,
    RuntimeError,
    httpx.HTTPError,
    YFRateLimitError,
)


def _is_finite(value: object) -> bool:
    try:
        return isfinite(float(value))
    except (TypeError, ValueError):
        return False


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


def _download_chart(
    symbol: str,
    *,
    period: str,
    interval: str = "1d",
    progress: bool = False,
    auto_adjust: bool = False,
) -> pd.DataFrame:
    """httpx 直连 Yahoo chart API 下载日线，返回与 yf.download 同构的 DataFrame。

    索引为美东时区的 DatetimeIndex，列为 Open/High/Low/Close/Volume；
    网络或解析失败抛 httpx.HTTPError / ValueError 等，由调用方降级。
    """
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        response = client.get(
            f"{_CHART_URL}/{symbol}",
            headers=_BROWSER_HEADERS,
            params={"interval": interval, "range": period},
        )
        response.raise_for_status()
        result = response.json()["chart"]["result"]
        if not result:
            raise ValueError("empty market-data response")
        data = result[0]
        timestamps = data.get("timestamp") or []
        quote = (data.get("indicators") or {}).get("quote") or [{}]
        quote = quote[0] or {}
        rows = {
            "Open": quote.get("open") or [],
            "High": quote.get("high") or [],
            "Low": quote.get("low") or [],
            "Close": quote.get("close") or [],
            "Volume": quote.get("volume") or [],
        }
        index = pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(
            "America/New_York"
        )
        return pd.DataFrame(rows, index=index)


class _ChartTicker:
    """httpx 直连 chart API 的轻量报价对象，提供与 yf.Ticker.fast_info 相同的接口。"""

    def __init__(self, symbol: str) -> None:
        self._symbol = symbol

    @property
    def fast_info(self) -> dict[str, float]:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.get(
                f"{_CHART_URL}/{self._symbol}",
                headers=_BROWSER_HEADERS,
                params={"interval": "1d", "range": "1d"},
            )
            response.raise_for_status()
            meta = response.json()["chart"]["result"][0]["meta"]
        return {
            "last_price": meta["regularMarketPrice"],
            "previous_close": meta["chartPreviousClose"],
        }


def fetch_daily_bars(
    symbol: str,
    period: str,
    downloader: Callable[..., object] | None = None,
    sleeper: Callable[[float], None] = sleep,
) -> tuple[list[PriceBar] | None, SourceStatus]:
    checked_at = datetime.now(UTC)
    if downloader is None:
        downloader = _download_chart
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
            if _is_finite(row.get("Close")) and _is_finite(row.get("Volume"))
        ]
        if not bars:
            raise ValueError("no finite close values in market-data response")
        return bars, SourceStatus(source="yahoo", available=True, checked_at=checked_at)
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
        httpx.HTTPError,
        YFRateLimitError,
    ) as error:
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
    ticker_factory: Callable[[str], object] | None = None,
    market_open: bool | None = None,
    sleeper: Callable[[float], None] = sleep,
) -> tuple[Quote | None, SourceStatus]:
    checked_at = datetime.now(UTC)
    if ticker_factory is None:
        ticker_factory = _ChartTicker
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
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
        httpx.HTTPError,
        YFRateLimitError,
    ) as error:
        return (
            None,
            SourceStatus(
                source="yahoo_quote",
                available=False,
                checked_at=checked_at,
                message=str(error),
            ),
        )

