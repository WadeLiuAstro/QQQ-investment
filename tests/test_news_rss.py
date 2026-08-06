"""news_rss 提供方测试：CNBC RSS 抓取与解析的降级行为。"""

from datetime import UTC, datetime

import httpx

from app.providers.news_rss import (
    CNBC_FEEDS,
    NewsItem,
    fetch_rss_headlines,
    parse_rss_items,
)


def _rss_xml(items: str) -> str:
    """构造最小 RSS 2.0 文档，items 为若干 <item> 片段。"""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<rss version=\"2.0\"><channel>"
        "<title>CNBC Test</title>"
        f"{items}"
        "</channel></rss>"
    )


def _item(title: str, link: str, pub_date: str) -> str:
    return (
        "<item>"
        f"<title>{title}</title>"
        f"<link>{link}</link>"
        f"<pubDate>{pub_date}</pubDate>"
        "</item>"
    )


def test_parse_rss_items_basic_fields_and_order() -> None:
    xml = _rss_xml(
        _item(
            "Fed holds rates steady",
            "https://www.cnbc.com/2026/08/06/fed.html",
            "Thu, 06 Aug 2026 13:30:00 GMT",
        )
        + _item(
            "Tech earnings beat",
            "https://www.cnbc.com/2026/08/06/tech.html",
            "Thu, 06 Aug 2026 10:00:00 GMT",
        )
    )

    items = parse_rss_items(xml, "CNBC 宏观")

    assert len(items) == 2
    assert items[0] == NewsItem(
        title="Fed holds rates steady",
        url="https://www.cnbc.com/2026/08/06/fed.html",
        published_at=datetime(2026, 8, 6, 13, 30, tzinfo=UTC),
        source="CNBC 宏观",
    )
    assert items[1].title == "Tech earnings beat"
    assert items[1].source == "CNBC 宏观"


def test_parse_rss_items_converts_pubdate_to_utc() -> None:
    xml = _rss_xml(
        _item(
            "Morning brief",
            "https://www.cnbc.com/brief.html",
            "Wed, 06 Aug 2026 03:00:05 GMT",
        )
    )

    items = parse_rss_items(xml, "CNBC 头条")

    assert items[0].published_at == datetime(2026, 8, 6, 3, 0, 5, tzinfo=UTC)
    assert items[0].published_at.utcoffset() is not None


def test_parse_rss_items_normalizes_non_utc_offset() -> None:
    xml = _rss_xml(
        _item(
            "Offshore update",
            "https://www.cnbc.com/offshore.html",
            "Wed, 06 Aug 2026 05:00:00 +0200",
        )
    )

    items = parse_rss_items(xml, "CNBC 宏观")

    # +0200 → UTC：05:00 - 2h = 03:00
    assert items[0].published_at == datetime(2026, 8, 6, 3, 0, tzinfo=UTC)


def test_parse_rss_items_naive_pubdate_treated_as_utc() -> None:
    xml = _rss_xml(
        _item(
            "Naive date story",
            "https://www.cnbc.com/naive.html",
            "06 Aug 2026 03:00:05",
        )
    )

    items = parse_rss_items(xml, "CNBC 宏观")

    assert items[0].published_at == datetime(2026, 8, 6, 3, 0, 5, tzinfo=UTC)


def test_parse_rss_items_unescapes_html_entities_in_title() -> None:
    xml = _rss_xml(
        _item(
            "Fed&apos;s call: &amp; what&apos;s next",
            "https://www.cnbc.com/fed.html",
            "Wed, 06 Aug 2026 03:00:05 GMT",
        )
    )

    items = parse_rss_items(xml, "CNBC 头条")

    assert items[0].title == "Fed's call: & what's next"


def test_parse_rss_items_skips_item_missing_link() -> None:
    xml = _rss_xml(
        "<item>"
        "<title>No link story</title>"
        "<pubDate>Wed, 06 Aug 2026 03:00:05 GMT</pubDate>"
        "</item>"
        + _item(
            "Valid story",
            "https://www.cnbc.com/valid.html",
            "Wed, 06 Aug 2026 04:00:05 GMT",
        )
    )

    items = parse_rss_items(xml, "CNBC 宏观")

    assert len(items) == 1
    assert items[0].title == "Valid story"


def test_parse_rss_items_skips_item_with_malformed_pubdate() -> None:
    xml = _rss_xml(
        _item("Bad date", "https://www.cnbc.com/bad.html", "not-a-date")
        + _item(
            "Good date",
            "https://www.cnbc.com/good.html",
            "Wed, 06 Aug 2026 03:00:05 GMT",
        )
    )

    items = parse_rss_items(xml, "CNBC 头条")

    assert len(items) == 1
    assert items[0].title == "Good date"


def test_parse_rss_items_malformed_xml_returns_empty_list() -> None:
    assert parse_rss_items("<rss><channel><item>", "CNBC 宏观") == []
    assert parse_rss_items("", "CNBC 宏观") == []


def test_parse_rss_items_empty_channel_returns_empty_list() -> None:
    assert parse_rss_items(_rss_xml(""), "CNBC 宏观") == []


def _ok_handler() -> object:
    """两源均 200 的 MockTransport handler。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url == CNBC_FEEDS[0][0]:
            return httpx.Response(
                200,
                text=_rss_xml(
                    _item(
                        "Macro story",
                        "https://www.cnbc.com/macro.html",
                        "Wed, 06 Aug 2026 03:00:05 GMT",
                    )
                ),
            )
        return httpx.Response(
            200,
            text=_rss_xml(
                _item(
                    "Top story",
                    "https://www.cnbc.com/top.html",
                    "Wed, 06 Aug 2026 05:00:05 GMT",
                )
            ),
        )

    return handler


def test_fetch_rss_headlines_merges_both_feeds() -> None:
    with httpx.Client(transport=httpx.MockTransport(_ok_handler())) as client:
        items, status = fetch_rss_headlines(client)

    assert status.source == "news_rss"
    assert status.available is True
    assert len(items) == 2
    assert {item.source for item in items} == {"CNBC 宏观", "CNBC 头条"}


def test_fetch_rss_headlines_sends_browser_headers() -> None:
    referers: list[str] = []
    user_agents: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        referers.append(request.headers.get("referer", ""))
        user_agents.append(request.headers.get("user-agent", ""))
        return httpx.Response(
            200,
            text=_rss_xml(
                _item(
                    "Story",
                    "https://www.cnbc.com/story.html",
                    "Wed, 06 Aug 2026 03:00:05 GMT",
                )
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        _, status = fetch_rss_headlines(client)

    assert status.available is True
    assert len(referers) == 2
    assert all(referer == "https://www.cnbc.com/" for referer in referers)
    assert all(agent.startswith("Mozilla/5.0") for agent in user_agents)


def test_fetch_rss_headlines_partial_failure_keeps_successful_feed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url == CNBC_FEEDS[0][0]:
            return httpx.Response(500, text="server error")
        return httpx.Response(
            200,
            text=_rss_xml(
                _item(
                    "Top story",
                    "https://www.cnbc.com/top.html",
                    "Wed, 06 Aug 2026 05:00:05 GMT",
                )
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        items, status = fetch_rss_headlines(client)

    assert status.available is True
    assert len(items) == 1
    assert items[0].source == "CNBC 头条"


def test_fetch_rss_headlines_all_failed_returns_unavailable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        items, status = fetch_rss_headlines(client)

    assert items == []
    assert status.available is False
    assert status.source == "news_rss"
    assert status.message


def test_fetch_rss_headlines_network_error_returns_unavailable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        items, status = fetch_rss_headlines(client)

    assert items == []
    assert status.available is False


def test_fetch_rss_headlines_malformed_body_does_not_raise() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<rss><channel><item>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        items, status = fetch_rss_headlines(client)

    assert items == []
    assert status.available is False
