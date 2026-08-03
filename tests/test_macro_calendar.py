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
    assert [(event.kind, event.event_at.date()) for event in events] == [
        ("nfp", date(2026, 9, 4)),
        ("cpi", date(2026, 9, 11)),
        ("fomc", date(2026, 9, 16)),
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
