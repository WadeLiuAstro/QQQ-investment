"""S1b: 结构性风险四维量化评分测试（体系 §5.1）。"""

from datetime import date, timedelta

from app.providers.yahoo import PriceBar
from app.services.structural import compute_structural_score


def _bars(close_values: list[float]) -> list[PriceBar]:
    start = date(2020, 1, 1)
    return [
        PriceBar(start + timedelta(days=i), close, 1_000_000, close, close, close)
        for i, close in enumerate(close_values)
    ]


def _flat_tail(n: int, tail: float) -> list[PriceBar]:
    """n 根 100.0 基准 + 1 根 tail。"""
    return _bars([100.0] * n + [tail])


def _peak_before(peak_days_ago: int, tail_price: float, total: int = 252) -> list[PriceBar]:
    """52 周窗口内最高点（110）出现在 peak_days_ago 个交易日前，其后为 tail_price。"""
    return _bars(
        [100.0] * (total - peak_days_ago - 1)
        + [110.0]
        + [tail_price] * peak_days_ago
    )


def _vix_series(consecutive_high: int, high_value: float = 30.0, low_value: float = 18.0) -> list[PriceBar]:
    return _bars([low_value] * 30 + [high_value] * consecutive_high)


def test_benign_market_scores_zero() -> None:
    qqq = _flat_tail(260, 102.0)
    qqqe = _flat_tail(260, 104.0)
    vix = _vix_series(0)
    score = compute_structural_score(qqq, qqqe, vix)
    assert score.available
    assert score.score == 0.0
    assert score.band == "normal"


def test_depth_scoring_increments_per_5pct() -> None:
    qqq = _flat_tail(260, 85.0)  # 回撤 -15%
    score = compute_structural_score(qqq, None, None)
    assert score.depth_score == 1.0

    qqq = _flat_tail(260, 80.0)  # 回撤 -20%
    score = compute_structural_score(qqq, None, None)
    assert score.depth_score == 2.0


def test_speed_scoring_gradual_bleed_gets_full_marks() -> None:
    qqq = _peak_before(45, 85.0)  # 慢性失血：高点在 45 个交易日前
    score = compute_structural_score(qqq, None, None)
    assert score.speed_score == 20.0


def test_speed_scoring_flash_crash_scores_zero() -> None:
    qqq = _peak_before(15, 85.0)  # 恐慌闪崩：高点在 15 个交易日前
    score = compute_structural_score(qqq, None, None)
    assert score.speed_score == 0.0


def test_speed_scoring_middle_band() -> None:
    qqq = _peak_before(30, 85.0)
    score = compute_structural_score(qqq, None, None)
    assert score.speed_score == 10.0


def test_width_scoring_requires_negative_rs_and_below_ma200() -> None:
    # QQQE 20 日跑输 QQQ（RS 为负），但 QQQ 仍在 MA200 之上 → 半分
    qqq = _flat_tail(260, 102.0)
    qqqe = _flat_tail(260, 98.0)
    score = compute_structural_score(qqq, qqqe, None)
    assert score.width_score == 12.5

    # QQQ 也跌破 MA200，且 QQQE 跌得比 QQQ 多（RS 为负）→ 满分
    qqq = _flat_tail(260, 85.0)
    qqqe = _flat_tail(260, 80.0)
    score = compute_structural_score(qqq, qqqe, None)
    assert score.width_score == 25.0


def test_vol_scoring_vix_regime_and_inversion() -> None:
    qqq = _flat_tail(260, 102.0)  # 良性市场基线，不贡献其他维度分数
    vix = _vix_series(10)  # 连续 10 日 > 25
    vix3m = _vix_series(0)
    score = compute_structural_score(qqq, None, vix, vix3m)
    assert score.vol_score == 25.0

    # 仅倒挂（VIX 连续不足 10 日，但 VIX/VIX3M > 1.2）
    vix = _vix_series(3, high_value=27.0)
    vix3m = _flat_tail(30, 20.0)
    score = compute_structural_score(qqq, None, vix, vix3m)
    assert score.vol_score == 10.0

    # 无倒挂无体制：VIX 28 但仅 3 日，VIX3M 25
    vix = _vix_series(3, high_value=28.0)
    vix3m = _flat_tail(30, 25.0)
    score = compute_structural_score(qqq, None, vix, vix3m)
    assert score.vol_score == 0.0


def test_band_watch_between_40_and_69() -> None:
    qqq = _flat_tail(260, 85.0)  # depth 1 + speed 20
    qqqe = _flat_tail(260, 98.0)  # width 12.5
    vix = _vix_series(10)
    vix3m = _vix_series(0)
    score = compute_structural_score(qqq, qqqe, vix, vix3m)
    assert score.score == 58.5
    assert score.band == "watch"


def test_band_critical_at_70() -> None:
    qqq = _peak_before(120, 5.0)  # 深度 17 + 速度 20
    qqqe = _peak_before(120, 3.0)  # RS 深度为负
    vix = _vix_series(10)
    vix3m = _vix_series(0)
    score = compute_structural_score(qqq, qqqe, vix, vix3m)
    assert score.band == "critical"
    assert score.score >= 70.0


def test_unavailable_with_insufficient_data() -> None:
    score = compute_structural_score(_bars([100.0] * 100), None, None)
    assert score.available is False
    assert score.band is None
