from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from app.models import SourceStatus


CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

# CNN 端点由 Varnish 反爬保护，无浏览器特征的请求返回 418；
# 携带常规浏览器头后返回 200。
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.cnn.com/markets/fear-and-greed",
}


@dataclass(frozen=True)
class FearGreedReading:
    score: int
    rating: str
    observed_at: datetime


def fetch_fear_greed(
    client: httpx.Client,
) -> tuple[FearGreedReading | None, SourceStatus]:
    checked_at = datetime.now(UTC)
    try:
        response = client.get(CNN_URL, timeout=8.0, headers=_BROWSER_HEADERS)
        response.raise_for_status()
        current = response.json()["fear_and_greed"]
        observed_at = datetime.fromisoformat(current["timestamp"].replace("Z", "+00:00"))
        return (
            FearGreedReading(
                score=int(current["score"]),
                rating=str(current["rating"]),
                observed_at=observed_at,
            ),
            SourceStatus(
                source="cnn_fear_greed",
                available=True,
                checked_at=checked_at,
            ),
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        return (
            None,
            SourceStatus(
                source="cnn_fear_greed",
                available=False,
                checked_at=checked_at,
                message=str(error),
            ),
        )
