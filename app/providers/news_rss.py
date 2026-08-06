"""CNBC RSS 新闻提供方：抓取并解析 RSS 2.0 头条，失败时优雅降级。"""

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from app.models import SourceStatus


# 两个 CNBC RSS 源：URL → 中文来源名。
CNBC_FEEDS = (
    (
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
        "CNBC 宏观",
    ),
    (
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "CNBC 头条",
    ),
)

# CNBC 对无浏览器特征的请求可能拒绝，携带常规浏览器头更稳定。
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.cnbc.com/",
}


@dataclass(frozen=True)
class NewsItem:
    """一条结构化头条：英文标题原样、中文来源名、UTC 发布时间。"""

    title: str
    url: str
    published_at: datetime
    source: str


def parse_rss_items(xml_text: str, source: str) -> list[NewsItem]:
    """解析 RSS 2.0 文档中的 <item> 列表。

    单个条目缺 title/link/pubDate 或日期畸形时跳过该条；
    XML 整体解析失败时返回空列表，绝不抛异常。
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    items: list[NewsItem] = []
    for item in root.iter("item"):
        parsed = _parse_single_item(item, source)
        if parsed is not None:
            items.append(parsed)
    return items


def _parse_single_item(item: ElementTree.Element, source: str) -> NewsItem | None:
    """解析单个 <item>；缺字段或日期畸形返回 None（由调用方跳过）。"""
    try:
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if not title or not url or not pub_date:
            return None
        # RFC 822 日期 → datetime，统一归一到 UTC；无时区标注时按 UTC 处理。
        published_at = parsedate_to_datetime(pub_date)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)
        published_at = published_at.astimezone(UTC)
        return NewsItem(
            title=title,
            url=url,
            published_at=published_at,
            source=source,
        )
    except (TypeError, ValueError):
        return None


def fetch_rss_headlines(
    client: httpx.Client,
) -> tuple[list[NewsItem], SourceStatus]:
    """依次抓取两个 CNBC RSS 源并合并解析结果。

    单源失败不影响另一源；至少一条成功即 available=True；
    全部失败或零条目时 available=False，绝不向外抛异常。
    """
    checked_at = datetime.now(UTC)
    headlines: list[NewsItem] = []
    errors: list[str] = []
    for url, source in CNBC_FEEDS:
        try:
            response = client.get(url, timeout=8.0, headers=_BROWSER_HEADERS)
            response.raise_for_status()
            headlines.extend(parse_rss_items(response.text, source))
        except (httpx.HTTPError, TypeError, ValueError) as error:
            errors.append(f"{source}: {error}")
    if headlines:
        return (
            headlines,
            SourceStatus(
                source="news_rss",
                available=True,
                checked_at=checked_at,
            ),
        )
    return (
        [],
        SourceStatus(
            source="news_rss",
            available=False,
            checked_at=checked_at,
            message="; ".join(errors) or "所有 RSS 源均无有效条目",
        ),
    )
