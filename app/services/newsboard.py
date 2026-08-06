"""消息面服务层：把宏观事件日历与 RSS 头条组装为 NewsBoard 卡片模型。

纯函数，不接调度、不做网络请求；任何输入缺失均优雅降级，绝不抛异常、绝不伪造数据。
"""

import math
from collections.abc import Sequence
from datetime import datetime, timedelta

from app.models import MacroEvent, NewsBoard, NewsHeadline, NewsUpcoming
from app.providers.news_rss import NewsItem

# 头条时间窗口：最近 3 天
HEADLINE_WINDOW_DAYS = 3
# 头条条数上限
HEADLINE_LIMIT = 12
# 预期事件条数上限：事件抓取窗口放宽到 35 天后，35 天窗口内事件数上限
UPCOMING_LIMIT = 10


def build_newsboard(
    events: Sequence[MacroEvent] | None,
    items: Sequence[NewsItem] | None,
    now: datetime,
    news_available: bool,
) -> NewsBoard:
    """组装消息面卡片。

    - events 为 None 表示事件日历抓取失败，upcoming 置空；
    - items 为 None/空表示无头条，仅做窗口过滤后为空；
    - news_available 反映 RSS 源整体状态，透传到 news_source_available；
    - available 仅在事件或头条至少其一有内容时为 True。
    """
    upcoming = _build_upcoming(events, now)
    headlines = _build_headlines(items, now)
    return NewsBoard(
        available=bool(upcoming or headlines),
        news_source_available=bool(news_available),
        upcoming=upcoming,
        headlines=headlines,
    )


def _build_upcoming(
    events: Sequence[MacroEvent] | None,
    now: datetime,
) -> list[NewsUpcoming]:
    """筛选未来事件：event_at > now，按时间升序取前 UPCOMING_LIMIT 个。

    days_until 为距今天数的向上取整（基于 total_seconds/86400），永不为负。
    """
    if not events:
        return []
    future = [event for event in events if event.event_at > now]
    future.sort(key=lambda event: event.event_at)
    rows: list[NewsUpcoming] = []
    for event in future[:UPCOMING_LIMIT]:
        delta_days = (event.event_at - now).total_seconds() / 86400
        rows.append(
            NewsUpcoming(
                kind=event.kind,
                title=event.title,
                event_at=event.event_at,
                days_until=max(math.ceil(delta_days), 0),
            )
        )
    return rows


def _build_headlines(
    items: Sequence[NewsItem] | None,
    now: datetime,
) -> list[NewsHeadline]:
    """过滤最近 HEADLINE_WINDOW_DAYS 天内的头条，按发布时间降序取前 HEADLINE_LIMIT 条。"""
    if not items:
        return []
    window_start = now - timedelta(days=HEADLINE_WINDOW_DAYS)
    fresh = [item for item in items if item.published_at >= window_start]
    fresh.sort(key=lambda item: item.published_at, reverse=True)
    return [
        NewsHeadline(
            title=item.title,
            url=item.url,
            source=item.source,
            published_at=item.published_at,
        )
        for item in fresh[:HEADLINE_LIMIT]
    ]
