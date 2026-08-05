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
class FearGreedPoint:
    observed_at: datetime
    score: float


@dataclass(frozen=True)
class FearGreedFactor:
    key: str
    label: str
    score: float
    rating: str | None = None


# 源 key → (稳定英文 key, 中文 label)；只解析这七个已确认的 CNN 因子。
_FACTOR_META = {
    "market_momentum_sp500": ("market_momentum", "市场动量"),
    "stock_price_strength": ("stock_price_strength", "股价强度"),
    "stock_price_breadth": ("stock_price_breadth", "市场宽度"),
    "put_call_options": ("put_call_options", "期权情绪"),
    "market_volatility_vix": ("market_volatility", "市场波动率"),
    "junk_bond_demand": ("junk_bond_demand", "垃圾债需求"),
    "safe_haven_demand": ("safe_haven_demand", "避险需求"),
}


@dataclass(frozen=True)
class FearGreedReading:
    score: int
    rating: str
    observed_at: datetime
    previous_close: float | None = None
    previous_week: float | None = None
    previous_month: float | None = None
    previous_year: float | None = None
    history: tuple[FearGreedPoint, ...] = ()
    factors: tuple[FearGreedFactor, ...] = ()


def fetch_fear_greed(
    client: httpx.Client,
) -> tuple[FearGreedReading | None, SourceStatus]:
    checked_at = datetime.now(UTC)
    try:
        response = client.get(CNN_URL, timeout=8.0, headers=_BROWSER_HEADERS)
        response.raise_for_status()
        data = response.json()
        current = data["fear_and_greed"]
        observed_at = datetime.fromisoformat(current["timestamp"].replace("Z", "+00:00"))
        reading = FearGreedReading(
            score=int(current["score"]),
            rating=str(current["rating"]),
            observed_at=observed_at,
            previous_close=_optional_float(current.get("previous_close")),
            previous_week=_optional_float(current.get("previous_1_week")),
            previous_month=_optional_float(current.get("previous_1_month")),
            previous_year=_optional_float(current.get("previous_1_year")),
            history=_parse_history(data),
            factors=_parse_factors(data),
        )
        return (
            reading,
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


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _parse_history(data: dict) -> tuple[FearGreedPoint, ...]:
    raw = data.get("fear_and_greed_historical")
    rows = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return ()
    points: list[FearGreedPoint] = []
    for row in rows:
        point = _parse_history_point(row)
        if point is not None:
            points.append(point)
    return tuple(points)


def _parse_history_point(row: object) -> FearGreedPoint | None:
    try:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            timestamp, score = row[0], row[1]
        elif isinstance(row, dict):
            timestamp, score = row.get("x"), row.get("y")
        else:
            return None
        observed_at = datetime.fromtimestamp(timestamp / 1000, tz=UTC)
        return FearGreedPoint(observed_at=observed_at, score=float(score))
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _parse_factors(data: dict) -> tuple[FearGreedFactor, ...]:
    factors: list[FearGreedFactor] = []
    for source_key, (key, label) in _FACTOR_META.items():
        raw = data.get(source_key)
        if not isinstance(raw, dict):
            continue
        score = _optional_float(raw.get("score"))
        if score is None:
            continue
        rating = raw.get("rating")
        factors.append(
            FearGreedFactor(
                key=key,
                label=label,
                score=score,
                rating=str(rating) if rating is not None else None,
            )
        )
    return tuple(factors)
