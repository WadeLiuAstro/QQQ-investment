from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from app.models import RuleConfig
from app.providers.yahoo import PriceBar
from app.services.decision import evaluate_decision
from app.services.indicators import calculate_indicators


@dataclass(frozen=True)
class BacktestResult:
    daily_states: list[str]
    equity_curve: list[float]
    cumulative_return: float
    max_drawdown: float
    turnover: float
    state_counts: dict[str, int]
    benchmark_return: float


def run_backtest(
    bars: Sequence[PriceBar], rules: RuleConfig, initial_capital: float = 10_000.0
) -> BacktestResult:
    portfolio_value = initial_capital
    benchmark_value = initial_capital
    previous_target = 40.0
    turnover = 0.0
    daily_states: list[str] = []
    equity_curve = [portfolio_value]

    for index in range(200, len(bars) - 1):
        decision = evaluate_decision(calculate_indicators(bars[: index + 1]), rules)
        next_day_return = bars[index + 1].close / bars[index].close - 1.0
        portfolio_value *= 1.0 + (decision.target_allocation / 100.0) * next_day_return
        benchmark_value *= 1.0 + 0.40 * next_day_return
        turnover += abs(decision.target_allocation - previous_target)
        previous_target = decision.target_allocation
        daily_states.append(decision.state)
        equity_curve.append(portfolio_value)

    return BacktestResult(
        daily_states=daily_states,
        equity_curve=equity_curve,
        cumulative_return=round((portfolio_value / initial_capital - 1.0) * 100, 2),
        max_drawdown=_max_drawdown(equity_curve),
        turnover=round(turnover, 2),
        state_counts=dict(Counter(daily_states)),
        benchmark_return=round((benchmark_value / initial_capital - 1.0) * 100, 2),
    )


def _max_drawdown(values: Sequence[float]) -> float:
    peak = values[0]
    drawdowns: list[float] = []
    for value in values:
        peak = max(peak, value)
        drawdowns.append((value / peak - 1.0) * 100)
    return round(min(drawdowns), 2)
