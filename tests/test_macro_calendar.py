from datetime import date

import httpx

from app.providers.macro_calendar import load_macro_events


def test_macro_calendar_loads_fomc_cpi_and_employment_events() -> None:
    fed_html = """
    <div class="fomc-meeting__date">September 15-16, 2026</div>
    """
    bls_html = """
    <table>
      <tr><td>Employment Situation</td><td>Friday, September 4, 2026</td></tr>
      <tr><td>Consumer Price Index</td><td>Friday, September 11, 2026</td></tr>
    </table>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if "federalreserve" in str(request.url):
            return httpx.Response(200, text=fed_html)
        return httpx.Response(200, text=bls_html)

    events, status = load_macro_events(
        httpx.Client(transport=httpx.MockTransport(handler)),
        start=date(2026, 9, 1),
        end=date(2026, 9, 30),
    )

    assert status.available is True
    assert status.message is None
    assert [(event.kind, event.event_at.date()) for event in events] == [
        ("nfp", date(2026, 9, 4)),
        ("cpi", date(2026, 9, 11)),
        ("fomc", date(2026, 9, 16)),
    ]


FED_HTML = """
    <div class="fomc-meeting__date">September 15-16, 2026</div>
    """
BLS_HTML = """
    <table>
      <tr><td>Employment Situation</td><td>Friday, September 4, 2026</td></tr>
      <tr><td>Consumer Price Index</td><td>Friday, September 11, 2026</td></tr>
    </table>
    """


def test_macro_calendar_bls_blocked_keeps_fomc_events() -> None:
    # BLS 被反爬封锁（403）时，FOMC 事件仍应正常返回
    def handler(request: httpx.Request) -> httpx.Response:
        if "federalreserve" in str(request.url):
            return httpx.Response(200, text=FED_HTML)
        return httpx.Response(403)

    events, status = load_macro_events(
        httpx.Client(transport=httpx.MockTransport(handler)),
        start=date(2026, 9, 1),
        end=date(2026, 9, 30),
    )

    assert status.available is True
    assert status.message is not None and "BLS" in status.message
    assert len(status.message) <= 200
    assert [(event.kind, event.event_at.date()) for event in events] == [
        ("fomc", date(2026, 9, 16)),
    ]


def test_macro_calendar_fomc_failure_keeps_bls_events() -> None:
    # FOMC 抓取失败时，BLS 事件仍应正常返回
    def handler(request: httpx.Request) -> httpx.Response:
        if "federalreserve" in str(request.url):
            return httpx.Response(503)
        return httpx.Response(200, text=BLS_HTML)

    events, status = load_macro_events(
        httpx.Client(transport=httpx.MockTransport(handler)),
        start=date(2026, 9, 1),
        end=date(2026, 9, 30),
    )

    assert status.available is True
    assert status.message is not None and "FOMC" in status.message
    assert [(event.kind, event.event_at.date()) for event in events] == [
        ("nfp", date(2026, 9, 4)),
        ("cpi", date(2026, 9, 11)),
    ]


def test_macro_calendar_source_failure_returns_unavailable_status() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    events, status = load_macro_events(
        httpx.Client(transport=httpx.MockTransport(handler)),
        start=date(2026, 9, 1),
        end=date(2026, 9, 30),
    )

    assert events is None
    assert status.available is False
    assert status.source == "macro_calendar"
    # 都失败时 message 需注明两个失败源
    assert status.message is not None
    assert "FOMC" in status.message and "BLS" in status.message
