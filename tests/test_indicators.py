from datetime import date, timedelta

from app.providers.yahoo import PriceBar
from app.services.indicators import calculate_indicators


def bars_from_closes(closes: list[float], volumes: list[int] | None = None) -> list[PriceBar]:
    start = date(2025, 1, 1)
    return [
        PriceBar(
            day=start + timedelta(days=index),
            close=close,
            volume=(volumes or [1_000_000] * len(closes))[index],
        )
        for index, close in enumerate(closes)
    ]


def test_wilder_rsi_uses_period_two_and_never_exposes_rsi_one() -> None:
    indicators = calculate_indicators(bars_from_closes(list(range(20, 8, -1))))

    assert indicators.rsi2 == 0.0
    assert indicators.rsi6 == 0.0
    assert not hasattr(indicators, "rsi1")


def test_intraday_price_marks_indicator_as_estimated() -> None:
    indicators = calculate_indicators(
        bars_from_closes(list(range(100, 351))), intraday_price=510.0
    )

    assert indicators.rsi_is_estimated is True
    assert indicators.current_price == 510.0
    assert indicators.moving_average_200 is not None


def test_indicator_calculates_drawdown_and_volume_ratio() -> None:
    closes = [100.0] * 199 + [120.0, 100.0]
    volumes = [1_000_000] * 200 + [3_000_000]

    indicators = calculate_indicators(bars_from_closes(closes, volumes))

    assert indicators.drawdown_pct == round((100.0 / 120.0 - 1.0) * 100, 2)
    assert indicators.volume_ratio == 3.0
