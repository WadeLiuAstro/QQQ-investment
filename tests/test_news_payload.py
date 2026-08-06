"""Task C: 消息面接入日频全量刷新路径的接线集成测试。"""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import MacroEvent, SourceStatus
from app.providers.news_rss import NewsItem
from app.providers.yahoo import PriceBar, Quote
from app.scheduler import collect_dashboard_payload
from app.services.dashboard import build_dashboard_payload
from app.providers.cnn_fear_greed import FearGreedReading


def bars(closes: list[float], start: date = date(2025, 1, 1)) -> list[PriceBar]:
    return [
        PriceBar(day=start + timedelta(days=index), close=close, volume=1_000_000)
        for index, close in enumerate(closes)
    ]


def status(source: str, available: bool = True) -> SourceStatus:
    return SourceStatus(source=source, available=available, checked_at=datetime.now(UTC))


def install_mocks(
    monkeypatch: pytest.MonkeyPatch,
    rss_side_effect=None,
    rss_result=None,
) -> None:
    """安装行情/恐贪/宏观的固定 mock；RSS 行为通过参数注入。"""
    rising = bars([100.0 + index * 0.5 for index in range(260)])
    vix = bars([16.0 + (index % 10) * 0.1 for index in range(260)])
    vix3m = bars([15.0 + (index % 10) * 0.05 for index in range(260)])

    def fake_bars(symbol: str, period: str):
        if symbol == "^VIX":
            return vix, status("yahoo")
        if symbol == "^VIX3M":
            return vix3m, status("yahoo")
        return rising, status("yahoo")

    def fake_quote(symbol: str):
        return (
            Quote(symbol=symbol, price=205.0, previous_close=200.0, is_intraday_estimate=False),
            status("yahoo_quote"),
        )

    def fake_fear_greed(client):
        return (
            FearGreedReading(score=50, rating="neutral", observed_at=datetime.now(UTC)),
            status("cnn_fear_greed"),
        )

    def fake_macro(client, start, end):
        # 给一个未来事件，便于验证 upcoming 组装
        event = MacroEvent(
            kind="cpi",
            title="CPI 公布",
            event_at=datetime.now(UTC) + timedelta(days=1),
            source="mock",
        )
        return [event], status("macro_calendar")

    def fake_rss(client):
        if rss_side_effect is not None:
            raise rss_side_effect
        return rss_result

    monkeypatch.setattr("app.scheduler.fetch_daily_bars", fake_bars)
    monkeypatch.setattr("app.scheduler.fetch_quote", fake_quote)
    monkeypatch.setattr("app.scheduler.fetch_fear_greed", fake_fear_greed)
    monkeypatch.setattr("app.scheduler.load_macro_events", fake_macro)
    monkeypatch.setattr("app.scheduler.fetch_rss_headlines", fake_rss)


def _strip_timestamps(value):
    """递归剔除所有 *_at 时间戳字段，便于跨两次抓取做结构化对比。"""
    if isinstance(value, dict):
        return {k: _strip_timestamps(v) for k, v in value.items() if not k.endswith("_at")}
    if isinstance(value, list):
        return [_strip_timestamps(item) for item in value]
    return value


def test_collect_payload_news_normal_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常路径：RSS 可用时 payload.news 非空且 available 字段符合预期。"""
    fresh_item = NewsItem(
        title="Fed holds rates steady",
        url="https://www.cnbc.com/2026/08/06/fed.html",
        published_at=datetime.now(UTC) - timedelta(hours=2),
        source="CNBC 宏观",
    )
    install_mocks(
        monkeypatch,
        rss_result=([fresh_item], status("news_rss", available=True)),
    )

    payload = collect_dashboard_payload(None)

    assert payload.news is not None
    assert payload.news.available is True
    assert payload.news.news_source_available is True
    assert len(payload.news.headlines) == 1
    assert payload.news.headlines[0].title == "Fed holds rates steady"
    # 宏观事件透传到 upcoming
    assert len(payload.news.upcoming) == 1
    assert payload.news.upcoming[0].title == "CPI 公布"
    # sources 中记录 news_rss 状态
    assert payload.sources["news_rss"].available is True


def test_collect_payload_rss_all_failed_decision_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RSS 全失败：news.news_source_available=False，正式字段与无 news 场景一致。"""
    install_mocks(
        monkeypatch,
        rss_result=([], status("news_rss", available=False)),
    )
    failed_payload = collect_dashboard_payload(None)

    assert failed_payload.news is not None
    assert failed_payload.news.news_source_available is False
    assert failed_payload.news.headlines == []
    assert failed_payload.decision is not None

    # 无 news 基线：RSS 抓取直接抛异常 → newsboard=None 且无 news_rss 键
    install_mocks(monkeypatch, rss_side_effect=RuntimeError("rss down"))
    baseline_payload = collect_dashboard_payload(None)
    assert baseline_payload.news is None
    assert "news_rss" not in baseline_payload.sources

    # 结构化对比：剔除 news 字段与 sources 中 news_rss 键、所有时间戳后应完全一致
    failed_dump = failed_payload.model_dump(mode="json")
    failed_dump.pop("news", None)
    failed_dump.get("sources", {}).pop("news_rss", None)
    baseline_dump = baseline_payload.model_dump(mode="json")
    baseline_dump.pop("news", None)
    assert _strip_timestamps(failed_dump) == _strip_timestamps(baseline_dump)


def test_build_dashboard_payload_default_news_none() -> None:
    """旧行为兼容：build_dashboard_payload 默认 news=None 时 payload.news 为 None。"""
    payload = build_dashboard_payload(
        generated_at=datetime(2026, 8, 6, 12, 0, tzinfo=UTC),
        sources={},
        market=None,
    )
    assert payload.news is None
