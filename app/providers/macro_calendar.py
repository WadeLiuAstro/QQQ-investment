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
    # FOMC 与 BLS 独立抓取，任一失败只降级该源，不牵连另一源
    fomc_events: list[MacroEvent] | None = None
    bls_events: list[MacroEvent] | None = None
    fomc_error: str | None = None
    bls_error: str | None = None
    try:
        fomc_response = client.get(FOMC_URL, timeout=8.0)
        fomc_response.raise_for_status()
        fomc_events = parse_fomc_events(fomc_response.text)
    except (httpx.HTTPError, TypeError, ValueError) as error:
        # 单源失败只记录错误信息，不抛出
        fomc_error = str(error)[:200]
    try:
        bls_response = client.get(BLS_URL, timeout=8.0)
        bls_response.raise_for_status()
        bls_events = parse_bls_events(bls_response.text)
    except (httpx.HTTPError, TypeError, ValueError) as error:
        bls_error = str(error)[:200]
    if fomc_events is None and bls_events is None:
        # 两源都失败才整体不可用
        return (
            None,
            SourceStatus(
                source="macro_calendar",
                available=False,
                checked_at=checked_at,
                message=f"FOMC: {fomc_error}; BLS: {bls_error}",
            ),
        )
    events = [*(fomc_events or []), *(bls_events or [])]
    events = [event for event in events if start <= event.event_at.date() <= end]
    events.sort(key=lambda event: event.event_at)
    # 部分成功时 message 注明失败源与原因，截断到 200 字符内
    message = None
    if fomc_error is not None:
        message = f"FOMC 不可用: {fomc_error}"[:200]
    if bls_error is not None:
        message = f"BLS 不可用: {bls_error}"[:200]
    return events, SourceStatus(
        source="macro_calendar",
        available=True,
        checked_at=checked_at,
        message=message,
    )


# Fed 日历页面新结构（2025 起改版）：
# - 每个年份一个分段，标题为 <h4><a id="数字">YYYY FOMC Meetings</a></h4>
# - 会议块内月份在 fomc-meeting__month 的 <strong> 中，
#   日期在其后独立的 fomc-meeting__date 块中，形如 "15-16" 或 "15-16*"
# - 会议日期语义取范围的结束日（如 15-16 取 16），决议公布时间为结束日 14:00（纽约时间）
_FOMC_YEAR_HEADER_PATTERN = re.compile(
    r'<h4>\s*<a id="\d+">(20\d\d) FOMC Meetings</a>\s*</h4>'
)
_FOMC_MONTH_PATTERN = re.compile(
    r"<strong>(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)</strong>"
)
_FOMC_DATE_PATTERN = re.compile(
    r"fomc-meeting__date[^>]*>\s*(\d{1,2})-(\d{1,2})\*?\s*<"
)


def parse_fomc_events(html: str) -> list[MacroEvent]:
    # 按年份标题位置切分段落：会议归入"其后最近的下一个年份标题之前"的区间，
    # 容忍年份标题与会议块之间的 HTML 噪声，避免跨年误配
    year_sections = [
        (int(match.group(1)), match.start())
        for match in _FOMC_YEAR_HEADER_PATTERN.finditer(html)
    ]
    month_matches = list(_FOMC_MONTH_PATTERN.finditer(html))
    events: list[MacroEvent] = []
    for index, month_match in enumerate(month_matches):
        year = _year_for_position(year_sections, month_match.start())
        if year is None:
            # 不在任何年份段内的月份无法归属，跳过
            continue
        # 只在本会议块到下一个月份块之间找最近的日期块，防止串块误配
        search_end = (
            month_matches[index + 1].start()
            if index + 1 < len(month_matches)
            else len(html)
        )
        date_match = _FOMC_DATE_PATTERN.search(html, month_match.end(), search_end)
        if date_match is None:
            # 畸形片段（有月份无日期块）跳过，不抛异常
            continue
        end_day = int(date_match.group(2))
        try:
            event_date = datetime.strptime(
                f"{month_match.group(1)} {end_day}, {year}", "%B %d, %Y"
            ).date()
        except ValueError:
            # 单个会议日期非法（如 2 月 30 日）跳过，整体不抛异常
            continue
        events.append(_event("fomc", "FOMC 利率决议", event_date, 14, 0, "federal_reserve"))
    return events


def _year_for_position(
    year_sections: list[tuple[int, int]], position: int
) -> int | None:
    # 返回该位置所属的年份：最后一个起始位置不超过 position 的年份段
    year = None
    for section_year, section_start in year_sections:
        if section_start <= position:
            year = section_year
        else:
            break
    return year


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

