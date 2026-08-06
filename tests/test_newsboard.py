"""消息面服务层测试：窗口过滤、条数上限、排序、days_until 计算与降级矩阵。"""

from datetime import UTC, datetime, timedelta

from app.models import DashboardPayload, MacroEvent
from app.providers.news_rss import NewsItem
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
    """upcoming：过去事件排除、升序、取前 3、days_until 向上取整。"""

    def test_past_events_excluded(self) -> None:
        board = build_newsboard(
            events=[_event("已过去的会议", NOW - timedelta(days=1))],
            items=[],
            now=NOW,
            news_available=True,
        )
        assert board.upcoming == []

    def test_upcoming_sorted_ascending_and_capped_at_three(self) -> None:
        events = [
            _event("第四个事件", NOW + timedelta(days=30)),
            _event("第一个事件", NOW + timedelta(days=1)),
            _event("第三个事件", NOW + timedelta(days=20)),
            _event("第二个事件", NOW + timedelta(days=10)),
        ]
        board = build_newsboard(events=events, items=[], now=NOW, news_available=True)
        assert len(board.upcoming) == UPCOMING_LIMIT == 3
        assert [u.title for u in board.upcoming] == [
            "第一个事件",
            "第二个事件",
            "第三个事件",
        ]
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
