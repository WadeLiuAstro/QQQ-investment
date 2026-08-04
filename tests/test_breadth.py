from datetime import date, timedelta

from app.providers.yahoo import PriceBar
from app.services.breadth import build_breadth


def bars(closes: list[float]) -> list[PriceBar]:
    start = date(2025, 1, 1)
    return [
        PriceBar(day=start + timedelta(days=index), close=close, volume=1_000_000)
        for index, close in enumerate(closes)
    ]


def test_relative_strength_calculated_for_5_and_20_days() -> None:
    # QQQ: 100 -> 110（+10%）；QQQE: 100 -> 104（+4%）→ RS 20d = -6
    qqq = bars([100.0] * 20 + [110.0])
    qqqe = bars([100.0] * 20 + [104.0])

    breadth = build_breadth(qqq, qqqe)

    assert breadth.available is True
    assert breadth.relative_strength_20d == round(4.0 - 10.0, 2)
    assert breadth.qqq_return_20d == 10.0
    assert breadth.qqqe_price == 104.0


def test_high_concentration_label_when_index_up_width_weak() -> None:
    # QQQ +10%，QQQE +4% → RS = -6 ≤ -1 → 上涨集中度偏高
    qqq = bars([100.0] * 20 + [110.0])
    qqqe = bars([100.0] * 20 + [104.0])

    breadth = build_breadth(qqq, qqqe)

    assert breadth.label == "上涨集中度偏高"


def test_equal_weight_leading_label() -> None:
    # QQQ +2%，QQQE +6% → RS = +4 ≥ 1 → 等权同步走强
    qqq = bars([100.0] * 20 + [102.0])
    qqqe = bars([100.0] * 20 + [106.0])

    breadth = build_breadth(qqq, qqqe)

    assert breadth.label == "等权同步走强"


def test_in_sync_label_when_rs_within_band() -> None:
    # QQQ +5%，QQQE +5.5% → RS = +0.5 → 宽度与指数同步
    qqq = bars([100.0] * 20 + [105.0])
    qqqe = bars([100.0] * 20 + [105.5])

    breadth = build_breadth(qqq, qqqe)

    assert breadth.label == "宽度与指数同步"


def test_downturn_label_when_index_falls() -> None:
    # QQQ -8%，QQQE -2% → 指数下跌 → 回调期宽度观察
    qqq = bars([100.0] * 20 + [92.0])
    qqqe = bars([100.0] * 20 + [98.0])

    breadth = build_breadth(qqq, qqqe)

    assert breadth.label == "回调期宽度观察"


def test_insufficient_data_marks_unavailable() -> None:
    breadth = build_breadth(bars([100.0] * 5), bars([100.0] * 5))

    assert breadth.available is False
    assert breadth.label is None
    assert breadth.note == "历史数据不足"


def test_missing_qqqe_marks_unavailable() -> None:
    breadth = build_breadth(bars([100.0] * 30), None)

    assert breadth.available is False
    assert breadth.note == "等权数据缺失"


def test_relative_strength_5d_uses_five_day_window() -> None:
    # QQQ 最近5日 100->110（+10%），QQQE 100->102（+2%）→ RS 5d = -8
    qqq = bars([100.0] * 25 + [110.0])
    qqqe = bars([100.0] * 25 + [102.0])

    breadth = build_breadth(qqq, qqqe)

    assert breadth.relative_strength_5d == round(2.0 - 10.0, 2)
