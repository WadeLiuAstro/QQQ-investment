from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from app.models import SourceStatus


CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"


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
        response = client.get(CNN_URL, timeout=8.0)
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
