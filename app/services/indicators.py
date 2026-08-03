from dataclasses import dataclass
from itertools import pairwise
from typing import Sequence

from app.providers.yahoo import PriceBar


@dataclass(frozen=True)
class IndicatorSet:
    current_price: float | None
    rsi2: float | None
    rsi6: float | None
    moving_average_200: float | None
    drawdown_pct: float | None
    volume_ratio: float | None
    rsi_is_estimated: bool
    vix: float | None = None
    fear_greed: float | None = None


def calculate_indicators(
    bars: Sequence[PriceBar], intraday_price: float | None = None
) -> IndicatorSet:
    closes = [bar.close for bar in bars]
    current_price = intraday_price if intraday_price is not None else (closes[-1] if closes else None)
    rsi_closes = closes[:-1] + [intraday_price] if intraday_price is not None and closes else closes
    moving_average_200 = _mean(closes[-200:]) if len(closes) >= 200 else None
    peak = max([*closes, intraday_price] if intraday_price is not None else closes, default=None)
    drawdown_pct = (
        round((current_price / peak - 1.0) * 100, 2)
        if current_price is not None and peak is not None
        else None
    )
    prior_volumes = [bar.volume for bar in bars[-21:-1]]
    volume_ratio = (
        round(bars[-1].volume / _mean(prior_volumes), 2) if len(prior_volumes) == 20 else None
    )
    return IndicatorSet(
        current_price=current_price,
        rsi2=_rounded_rsi(rsi_closes, 2),
        rsi6=_rounded_rsi(rsi_closes, 6),
        moving_average_200=round(moving_average_200, 2) if moving_average_200 is not None else None,
        drawdown_pct=drawdown_pct,
        volume_ratio=volume_ratio,
        rsi_is_estimated=intraday_price is not None,
    )


def wilders_rsi(closes: Sequence[float], period: int) -> float | None:
    if period < 2 or len(closes) <= period:
        return None
    changes = list(pairwise(closes))
    gains = [max(current - previous, 0.0) for previous, current in changes]
    losses = [max(previous - current, 0.0) for previous, current in changes]
    average_gain = _mean(gains[:period])
    average_loss = _mean(losses[:period])
    for gain, loss in zip(gains[period:], losses[period:]):
        average_gain = ((average_gain * (period - 1)) + gain) / period
        average_loss = ((average_loss * (period - 1)) + loss) / period
    if average_loss == 0:
        return 100.0
    return 100 - (100 / (1 + average_gain / average_loss))


def _rounded_rsi(closes: Sequence[float], period: int) -> float | None:
    value = wilders_rsi(closes, period)
    return round(value, 2) if value is not None else None


def _mean(values: Sequence[float | int]) -> float:
    return sum(values) / len(values)

