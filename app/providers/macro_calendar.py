import re
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import httpx

from app.models import MacroEvent, SourceStatus

FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BLS_URL = "https://www.bls.gov/schedule/news_release/"
NEW_YORK = ZoneInfo("America/New_York")


def load_macro_events(
    client: httpx.Client,
    start: date,
    end: date,
) -> tuple[list[MacroEvent] | None, SourceStatus]:
    checked_at = datetime.now(UTC)
    try:
        fomc_response = client.get(FOMC_URL, timeout=8.0)
        fomc_response.raise_for_status()
        bls_response = client.get(BLS_URL, timeout=8.0)
        bls_response.raise_for_status()
        events = [
            *parse_fomc_events(fomc_response.text),
            *parse_bls_events(bls_response.text),
        ]
        events = [event for event in events if start <= event.event_at.date() <= end]
        events.sort(key=lambda event: event.event_at)
        return events, SourceStatus(
            source="macro_calendar", available=True, checked_at=checked_at
        )
    except (httpx.HTTPError, TypeError, ValueError) as error:
        return (
            None,
            SourceStatus(
                source="macro_calendar",
                available=False,
                checked_at=checked_at,
                message=str(error),
            ),
        )


def parse_fomc_events(html: str) -> list[MacroEvent]:
    events: list[MacroEvent] = []
    for match in re.finditer(
        r'fomc-meeting__date[^>]*>\s*([A-Za-z]+)\s+\d{1,2}-(\d{1,2}),\s*(\d{4})',
        html,
    ):
        month, end_day, year = match.groups()
        event_date = datetime.strptime(
            f"{month} {end_day}, {year}", "%B %d, %Y"
        ).date()
        events.append(_event("fomc", "FOMC 利率决议", event_date, 14, 0, "federal_reserve"))
    return events


def parse_bls_events(html: str) -> list[MacroEvent]:
    events: list[MacroEvent] = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.DOTALL | re.IGNORECASE)
    for row in rows:
        text = re.sub(r"<[^>]+>", " ", row)
        normalized = " ".join(text.split())
        kind_and_title = (
            ("nfp", "非农就业报告", "Employment Situation"),
            ("cpi", "CPI 数据公布", "Consumer Price Index"),
        )
        for kind, title, marker in kind_and_title:
            if marker not in normalized:
                continue
            match = re.search(
                r"(?:Monday|Tuesday|Wednesday|Thursday|Friday),\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
                normalized,
            )
            if match:
                event_date = datetime.strptime(match.group(1), "%B %d, %Y").date()
                events.append(_event(kind, title, event_date, 8, 30, "bls"))
    return events


def _event(
    kind: str,
    title: str,
    event_date: date,
    hour: int,
    minute: int,
    source: str,
) -> MacroEvent:
    return MacroEvent(
        kind=kind,
        title=title,
        event_at=datetime(
            event_date.year,
            event_date.month,
            event_date.day,
            hour,
            minute,
            tzinfo=NEW_YORK,
        ),
        source=source,
    )

