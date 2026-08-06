"""消息面服务层测试：窗口过滤、条数上限、排序、days_until 计算与降级矩阵。

并覆盖调度层接线：事件窗口放宽到 35 天后 news.upcoming 上限 10，
且传给监控区的事件仍按 7 天预过滤。
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import DashboardPayload, MacroEvent, SourceStatus
from app.providers.cnn_fear_greed import FearGreedReading
from app.providers.news_rss import NewsItem
from app.providers.yahoo import PriceBar, Quote
from app.scheduler import collect_dashboard_payload
from app.services.newsboard import (
    HEADLINE_LIMIT,
    HEADLINE_WINDOW_DAYS,
    UPCOMING_LIMIT,
    build_newsboard,
)

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


def _item(title: str, published_at: datetime, source: str = "CNBC 头条") -> NewsItem:
    """构造一条测试头条。"""
    return NewsItem(
        title=title,
        url=f"https://example.com/{title}",
        published_at=published_at,
        source=source,
    )


def _event(title: str, event_at: datetime, kind: str = "FOMC") -> MacroEvent:
    """构造一条测试宏观事件。"""
    return MacroEvent(kind=kind, title=title, event_at=event_at, source="测试日历")


class TestHeadlineWindow:
    """3 天窗口：窗口内保留、窗口外过滤。"""

    def test_headline_within_window_kept(self) -> None:
        board = build_newsboard(
            events=[],
            items=[_item("两天前头条", NOW - timedelta(days=2))],
            now=NOW,
            news_available=True,
        )
        assert [h.title for h in board.headlines] == ["两天前头条"]
        assert board.available is True

    def test_headline_outside_window_filtered(self) -> None:
        board = build_newsboard(
            events=[],
            items=[_item("四天前头条", NOW - timedelta(days=4))],
            now=NOW,
            news_available=True,
        )
        assert board.headlines == []
        assert board.available is False

    def test_window_boundary_kept(self) -> None:
        # 恰好 3 天前（含边界）按契约 published_at >= now - 3 天 应保留
        board = build_newsboard(
            events=[],
            items=[_item("边界头条", NOW - timedelta(days=HEADLINE_WINDOW_DAYS))],
            now=NOW,
            news_available=True,
        )
        assert [h.title for h in board.headlines] == ["边界头条"]


class TestHeadlineLimitAndOrder:
    """上限 12 条、按发布时间降序。"""

    def test_fifteen_headlines_keep_latest_twelve_descending(self) -> None:
        # 15 条窗口内头条：发布时间从 1 小时前到 15 小时前（越早越旧）
        items = [
            _item(f"头条{i:02d}", NOW - timedelta(hours=i)) for i in range(1, 16)
        ]
        board = build_newsboard(
            events=[], items=items, now=NOW, news_available=True
        )
        assert len(board.headlines) == HEADLINE_LIMIT == 12
        # 保留的是最新 12 条（1~12 小时前），最旧的 3 条被裁掉
        assert [h.title for h in board.headlines] == [
            f"头条{i:02d}" for i in range(1, 13)
        ]
        # 严格降序
        times = [h.published_at for h in board.headlines]
        assert times == sorted(times, reverse=True)

    def test_headline_fields_mapped(self) -> None:
        published = NOW - timedelta(hours=5)
        board = build_newsboard(
            events=[],
            items=[_item("标题原文", published, source="CNBC 宏观")],
            now=NOW,
            news_available=True,
        )
        headline = board.headlines[0]
        assert headline.title == "标题原文"
        assert headline.url == "https://example.com/标题原文"
        assert headline.source == "CNBC 宏观"
        assert headline.published_at == published


class TestUpcoming:
    """upcoming：过去事件排除、升序、取前 10、days_until 向上取整。"""

    def test_past_events_excluded(self) -> None:
        board = build_newsboard(
            events=[_event("已过去的会议", NOW - timedelta(days=1))],
            items=[],
            now=NOW,
            news_available=True,
        )
        assert board.upcoming == []

    def test_upcoming_sorted_ascending_and_capped_at_ten(self) -> None:
        # 上限从 3 放宽到 10（服务 35 天窗口消息面日历），4 个事件全部保留且升序
        events = [
            _event("第四个事件", NOW + timedelta(days=30)),
            _event("第一个事件", NOW + timedelta(days=1)),
            _event("第三个事件", NOW + timedelta(days=20)),
            _event("第二个事件", NOW + timedelta(days=10)),
        ]
        board = build_newsboard(events=events, items=[], now=NOW, news_available=True)
        assert len(board.upcoming) == 4
        assert UPCOMING_LIMIT == 10
        assert [u.title for u in board.upcoming] == [
            "第一个事件",
            "第二个事件",
            "第三个事件",
            "第四个事件",
        ]
        times = [u.event_at for u in board.upcoming]
        assert times == sorted(times)

    def test_twelve_future_events_keep_first_ten_ascending(self) -> None:
        # 12 个未来事件（乱序）：按时间升序只取前 10 个，最晚 2 个被裁掉
        offsets = [2, 30, 5, 33, 1, 20, 12, 25, 8, 15, 34, 28]
        events = [_event(f"事件{i:02d}", NOW + timedelta(days=day)) for i, day in enumerate(offsets, start=1)]
        board = build_newsboard(events=events, items=[], now=NOW, news_available=True)
        assert len(board.upcoming) == UPCOMING_LIMIT == 10
        kept_days = sorted(offsets)[:10]
        assert [u.days_until for u in board.upcoming] == kept_days
        times = [u.event_at for u in board.upcoming]
        assert times == sorted(times)

    def test_days_until_ceil_rounding(self) -> None:
        # now = 2026-08-06T12:00Z
        board = build_newsboard(
            events=[
                _event("六天半后", datetime(2026, 8, 12, 12, 30, tzinfo=UTC)),  # → 7
                _event("两小时后", datetime(2026, 8, 6, 14, 0, tzinfo=UTC)),  # → 1
            ],
            items=[],
            now=NOW,
            news_available=True,
        )
        by_title = {u.title: u for u in board.upcoming}
        assert by_title["六天半后"].days_until == 7
        assert by_title["两小时后"].days_until == 1

    def test_upcoming_fields_mapped(self) -> None:
        event_at = NOW + timedelta(days=2)
        board = build_newsboard(
            events=[_event("CPI 数据", event_at, kind="CPI")],
            items=[],
            now=NOW,
            news_available=True,
        )
        row = board.upcoming[0]
        assert row.kind == "CPI"
        assert row.title == "CPI 数据"
        assert row.event_at == event_at
        assert row.days_until == 2


class TestDegradationMatrix:
    """降级矩阵：日历失败、新闻源失败、双失败均不抛异常且不伪造数据。"""

    def test_all_sources_failed_unavailable(self) -> None:
        board = build_newsboard(
            events=None, items=[], now=NOW, news_available=False
        )
        assert board.available is False
        assert board.news_source_available is False
        assert board.upcoming == []
        assert board.headlines == []

    def test_calendar_failed_but_headlines_available(self) -> None:
        board = build_newsboard(
            events=None,
            items=[_item("仅头条", NOW - timedelta(hours=6))],
            now=NOW,
            news_available=True,
        )
        assert board.available is True
        assert board.upcoming == []
        assert len(board.headlines) == 1

    def test_news_source_failed_but_calendar_available(self) -> None:
        board = build_newsboard(
            events=[_event("FOMC 议息", NOW + timedelta(days=5))],
            items=[],
            now=NOW,
            news_available=False,
        )
        assert board.available is True
        assert board.news_source_available is False
        assert len(board.upcoming) == 1
        assert board.headlines == []

    def test_none_items_safe(self) -> None:
        # 极端防御：items 为 None 也不抛异常
        board = build_newsboard(
            events=[], items=None, now=NOW, news_available=False
        )
        assert board.available is False
        assert board.headlines == []


class TestPayloadCompatibility:
    """模型兼容：旧快照 JSON 无 news 字段时 model_validate 通过且 news 为 None。"""

    def test_legacy_payload_without_news_validates(self) -> None:
        legacy = {
            "generated_at": "2026-08-04T12:00:00Z",
            "sources": {
                "yahoo": {
                    "source": "yahoo",
                    "available": True,
                    "checked_at": "2026-08-04T12:00:00Z",
                }
            },
            "market": {"qqq": {"symbol": "QQQ", "price": 500.0}},
        }
        payload = DashboardPayload.model_validate(legacy)
        assert payload.news is None

    def test_payload_with_news_validates(self) -> None:
        data = {
            "generated_at": "2026-08-06T12:00:00Z",
            "sources": {},
            "news": {
                "available": True,
                "news_source_available": True,
                "upcoming": [
                    {
                        "kind": "FOMC",
                        "title": "FOMC 议息",
                        "event_at": "2026-08-12T12:30:00Z",
                        "days_until": 7,
                    }
                ],
                "headlines": [
                    {
                        "title": "Headline",
                        "url": "https://example.com/a",
                        "source": "CNBC 头条",
                        "published_at": "2026-08-06T08:00:00Z",
                    }
                ],
            },
        }
        payload = DashboardPayload.model_validate(data)
        assert payload.news is not None
        assert payload.news.available is True
        assert payload.news.upcoming[0].days_until == 7
        assert payload.news.headlines[0].source == "CNBC 头条"


# ---------------------------------------------------------------------------
# 调度层接线：35 天事件窗口 + 监控区 7 天预过滤
# ---------------------------------------------------------------------------


def _bars(closes: list[float], start: date = date(2025, 1, 1)) -> list[PriceBar]:
    return [
        PriceBar(day=start + timedelta(days=index), close=close, volume=1_000_000)
        for index, close in enumerate(closes)
    ]


def _status(source: str, available: bool = True) -> SourceStatus:
    return SourceStatus(source=source, available=available, checked_at=datetime.now(UTC))


def test_scheduler_wide_window_upcoming_and_monitoring_prefilter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """35 天窗口事件（+10/+20 天）进入 news.upcoming；监控区只保留 ≤7 天事件。"""
    captured: dict[str, date] = {}
    now = datetime.now(UTC)

    def fake_macro(client, start, end):
        # 记录调度层传入的窗口参数，验证已放宽到 35 天
        captured["start"] = start
        captured["end"] = end
        return [
            MacroEvent(kind="cpi", title="三天后 CPI", event_at=now + timedelta(days=3), source="mock"),
            MacroEvent(kind="fomc", title="十天后 FOMC", event_at=now + timedelta(days=10), source="mock"),
            MacroEvent(kind="nonfarm", title="二十天后非农", event_at=now + timedelta(days=20), source="mock"),
        ], _status("macro_calendar")

    rising = _bars([100.0 + index * 0.5 for index in range(260)])
    vix = _bars([16.0 + (index % 10) * 0.1 for index in range(260)])
    vix3m = _bars([15.0 + (index % 10) * 0.05 for index in range(260)])

    def fake_bars(symbol: str, period: str):
        if symbol == "^VIX":
            return vix, _status("yahoo")
        if symbol == "^VIX3M":
            return vix3m, _status("yahoo")
        return rising, _status("yahoo")

    def fake_quote(symbol: str):
        return (
            Quote(symbol=symbol, price=205.0, previous_close=200.0, is_intraday_estimate=False),
            _status("yahoo_quote"),
        )

    def fake_fear_greed(client):
        return (
            FearGreedReading(score=50, rating="neutral", observed_at=datetime.now(UTC)),
            _status("cnn_fear_greed"),
        )

    monkeypatch.setattr("app.scheduler.fetch_daily_bars", fake_bars)
    monkeypatch.setattr("app.scheduler.fetch_quote", fake_quote)
    monkeypatch.setattr("app.scheduler.fetch_fear_greed", fake_fear_greed)
    monkeypatch.setattr("app.scheduler.load_macro_events", fake_macro)
    monkeypatch.setattr(
        "app.scheduler.fetch_rss_headlines", lambda client: ([], _status("news_rss"))
    )

    payload = collect_dashboard_payload(None)

    # 1. 抓取窗口放宽到 35 天（服务消息面日历）
    assert (captured["end"] - captured["start"]).days == 35

    # 2. 35 天窗口内的远期事件（+10/+20 天）也进入 news.upcoming
    assert payload.news is not None
    upcoming_titles = [u.title for u in payload.news.upcoming]
    assert upcoming_titles == ["三天后 CPI", "十天后 FOMC", "二十天后非农"]

    # 3. 监控区"临近高影响事件"只保留 ≤7 天事件，保持"临近"语义
    monitoring = payload.monitoring
    assert monitoring is not None
    macro_events = monitoring.groups["macro_defensive"].details.events
    assert [e.title for e in macro_events] == ["三天后 CPI"]
