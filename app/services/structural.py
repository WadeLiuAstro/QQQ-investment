"""S1b: 结构性风险四维量化评分（体系 §5.1）。

四个维度：回撤深度（30）、回撤速度（20）、宽度恶化（25）、波动率体制（25）。
判读：≥ 70 疑似结构性风险；40–69 警示（加仓减半）；< 40 视为流动性恐慌。
宏观因子作辅助交叉验证，不纳入主评分。
"""

from dataclasses import dataclass
from typing import Sequence

from app.providers.yahoo import PriceBar

_WINDOW_52W = 252
_MA_WINDOW = 200

_DEPTH_START_PCT = 15.0
_DEPTH_STEP_PCT = 5.0
_DEPTH_MAX = 30.0

_SPEED_SLOW_DAYS = 40
_SPEED_MID_DAYS = 20
_SPEED_MAX = 20.0

_WIDTH_RS_HALF = 12.5
_WIDTH_BELOW_MA200_HALF = 12.5

_VIX_HIGH_DAYS = 10
_VIX_HIGH_LEVEL = 25.0
_VIX_TERM_INVERT = 1.2
_VOL_REGIME_SCORE = 15.0
_VOL_INVERSION_SCORE = 10.0

_BAND_CRITICAL = 70.0
_BAND_WATCH = 40.0


@dataclass(frozen=True)
class StructuralScore:
    available: bool
    score: float | None = None
    band: str | None = None  # "normal" | "watch" | "critical"
    depth_score: float = 0.0
    speed_score: float = 0.0
    width_score: float = 0.0
    vol_score: float = 0.0
    note: str | None = None


def compute_structural_score(
    qqq_bars: Sequence[PriceBar] | None,
    qqqe_bars: Sequence[PriceBar] | None,
    vix_bars: Sequence[PriceBar] | None,
    vix3m_bars: Sequence[PriceBar] | None = None,
) -> StructuralScore:
    """四维结构性风险评分；QQQ 数据不足时整体不可用。"""
    if not qqq_bars or len(qqq_bars) < _WINDOW_52W:
        return StructuralScore(available=False, note="QQQ 历史数据不足 252 日")

    closes = [bar.close for bar in qqq_bars[-_WINDOW_52W:]]
    price = closes[-1]
    peak = max(closes)

    # 1) 回撤深度：距 52 周高点回撤 ≥ 15% 起计，每深 5% 加一分（满分 30）
    drawdown_pct = round((price / peak - 1.0) * 100, 6)
    if drawdown_pct <= -_DEPTH_START_PCT:
        depth_score = min(
            _DEPTH_MAX, int((abs(drawdown_pct) - _DEPTH_START_PCT) // _DEPTH_STEP_PCT) + 1
        )
    else:
        depth_score = 0.0

    # 2) 回撤速度：高点距今 > 40 交易日为慢性失血（满分 20），< 20 为恐慌闪崩（0 分）
    if price >= peak:
        speed_score = 0.0
    else:
        peak_idx = closes.index(peak)
        days_from_peak = len(closes) - 1 - peak_idx
        if days_from_peak > _SPEED_SLOW_DAYS:
            speed_score = _SPEED_MAX
        elif days_from_peak > _SPEED_MID_DAYS:
            speed_score = _SPEED_MAX / 2
        else:
            speed_score = 0.0

    # 3) 宽度恶化：QQQE/QQQ 相对强弱 20 日为负 且 QQQ 低于 MA200（满分 25）
    width_score = 0.0
    rs_20d = _rs_20d(qqq_bars, qqqe_bars)
    if rs_20d is not None and rs_20d < 0:
        width_score += _WIDTH_RS_HALF
    ma200 = sum(closes[-_MA_WINDOW:]) / _MA_WINDOW
    if price < ma200:
        width_score += _WIDTH_BELOW_MA200_HALF

    # 4) 波动率体制：VIX 连续 10 日 > 25（15 分），或 VIX/VIX3M > 1.2 期限倒挂（10 分）
    vol_score = 0.0
    if vix_bars:
        vix_closes = [bar.close for bar in vix_bars]
        recent = vix_closes[-_VIX_HIGH_DAYS:]
        if len(recent) == _VIX_HIGH_DAYS and all(v > _VIX_HIGH_LEVEL for v in recent):
            vol_score += _VOL_REGIME_SCORE
        vix_now = vix_closes[-1]
        vix3m_now = vix3m_bars[-1].close if vix3m_bars else None
        if vix_now is not None and vix3m_now is not None and vix3m_now > 0:
            if vix_now / vix3m_now > _VIX_TERM_INVERT:
                vol_score += _VOL_INVERSION_SCORE

    score = depth_score + speed_score + width_score + vol_score
    if score >= _BAND_CRITICAL:
        band = "critical"
    elif score >= _BAND_WATCH:
        band = "watch"
    else:
        band = "normal"

    return StructuralScore(
        available=True,
        score=round(score, 1),
        band=band,
        depth_score=float(depth_score),
        speed_score=speed_score,
        width_score=width_score,
        vol_score=vol_score,
    )


def _rs_20d(
    qqq_bars: Sequence[PriceBar], qqqe_bars: Sequence[PriceBar] | None
) -> float | None:
    """QQQE 相对 QQQ 的 20 日收益差（百分点）。"""
    if not qqqe_bars or len(qqq_bars) < 21 or len(qqqe_bars) < 21:
        return None
    qqq_return = qqq_bars[-1].close / qqq_bars[-21].close - 1.0
    qqqe_return = qqqe_bars[-1].close / qqqe_bars[-21].close - 1.0
    return (qqqe_return - qqq_return) * 100
