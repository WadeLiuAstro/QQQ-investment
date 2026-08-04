from typing import Sequence

from app.models import Breadth
from app.providers.yahoo import PriceBar

# 相对强弱阈值（百分点）：|RS| <= 1 视为同步；QQQ 上涨且 RS <= -1 视为集中度偏高
_RS_BAND = 1.0


def build_breadth(
    qqq_bars: Sequence[PriceBar] | None, qqqe_bars: Sequence[PriceBar] | None
) -> Breadth:
    """计算 QQQE（等权）相对 QQQ 的 5/20 日强弱与集中度标签（仅佐证，不参与决策）。"""
    if not qqqe_bars:
        return Breadth(available=False, note="等权数据缺失")
    qqqe_price = _return_pct(qqqe_bars, 20)
    qqq_return_20 = _return_pct(qqq_bars, 20)
    rs_5d = _relative_strength(qqq_bars, qqqe_bars, 5)
    rs_20d = _relative_strength(qqq_bars, qqqe_bars, 20)
    if None in (qqqe_price, qqq_return_20, rs_5d, rs_20d):
        return Breadth(available=False, note="历史数据不足")
    return Breadth(
        qqqe_price=float(qqqe_bars[-1].close),
        relative_strength_5d=rs_5d,
        relative_strength_20d=rs_20d,
        qqq_return_20d=qqq_return_20,
        label=_label(qqq_return_20, rs_20d),
    )


def _relative_strength(
    qqq_bars: Sequence[PriceBar] | None,
    qqqe_bars: Sequence[PriceBar] | None,
    window: int,
) -> float | None:
    qqq_return = _return_pct(qqq_bars, window)
    qqqe_return = _return_pct(qqqe_bars, window)
    if qqq_return is None or qqqe_return is None:
        return None
    return round(qqqe_return - qqq_return, 2)


def _return_pct(bars: Sequence[PriceBar] | None, window: int) -> float | None:
    if not bars or len(bars) < window + 1:
        return None
    return round((bars[-1].close / bars[-window - 1].close - 1.0) * 100, 2)


def _label(qqq_return_20d: float, rs_20d: float) -> str:
    if qqq_return_20d <= 0:
        return "回调期宽度观察"
    if rs_20d <= -_RS_BAND:
        return "上涨集中度偏高"
    if rs_20d >= _RS_BAND:
        return "等权同步走强"
    return "宽度与指数同步"
