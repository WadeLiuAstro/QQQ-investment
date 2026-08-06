import re
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import httpx

from app.models import MacroEvent, SourceStatus

FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
# BLS 日历已改版：/schedule/news_release/ 仅 302 到当月页，直接按月份 URL 抓取
# https://www.bls.gov/schedule/{year}/{month:02d}_sched.htm
NEW_YORK = ZoneInfo("America/New_York")

# BLS 由 Akamai 反爬网关保护：仅带 UA 仍返回 403，需要完整浏览器特征头
# （含 Sec-Fetch-*、Upgrade-Insecure-Requests 等）才能放行；Fed 站点同样适用。
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


def _get_with_redirect(client: httpx.Client, url: str) -> httpx.Response:
    """GET 并手动跟随重定向（BLS 页面会 302 跳到当月排期页）。

    外部传入的 client 默认不跟随重定向，这里最多跟随 3 跳；
    无 location 头或超过跳数上限时返回最后一次响应。
    """
    response = client.get(url, timeout=8.0, headers=_BROWSER_HEADERS)
    hops = 0
    while response.is_redirect and hops < 3:
        location = response.headers.get("location")
        if not location:
            break
        response = client.get(
            response.url.join(location), timeout=8.0, headers=_BROWSER_HEADERS
        )
        hops += 1
    return response


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
        fomc_response = _get_with_redirect(client, FOMC_URL)
        fomc_response.raise_for_status()
        fomc_events = parse_fomc_events(fomc_response.text)
    except (httpx.HTTPError, TypeError, ValueError) as error:
        # 单源失败只记录错误信息，不抛出
        fomc_error = str(error)[:200]
    try:
        bls_events = _fetch_bls_events(client, start)
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
# - 会议块内月份在带 fomc-meeting__month 类名（容忍其他类与空白）的 div 后的
#   <strong> 中（允许中间 HTML 噪声），日期在其后独立的 fomc-meeting__date 块中，
#   形如 "15-16" 或 "15-16*"
# - 会议日期语义取范围的结束日（如 15-16 取 16），决议公布时间为结束日 14:00（纽约时间）
_FOMC_YEAR_HEADER_PATTERN = re.compile(
    r'<h4>\s*<a id="\d+">(20\d\d) FOMC Meetings</a>\s*</h4>'
)
# 锚定 fomc-meeting__month 类名，避免页面其他位置的 <strong>月份</strong> 文本被误配
_FOMC_MONTH_PATTERN = re.compile(
    r"fomc-meeting__month[^>]*>\s*(?:<[^>]+>\s*)*<strong>(January|February|March|"
    r"April|May|June|July|August|September|October|November|December)</strong>"
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


_BLS_CELL_PATTERN = re.compile(r'<td[^>]*id="d(\d{4})"[^>]*>(.*?)</td>', re.DOTALL)
_BLS_TIME_PATTERN = re.compile(r"(\d{1,2}):(\d{2}) (AM|PM)")
# 只解析这两个已确认的高影响事件；页面同时含 JOLTS/进出口价格等低影响条目
_BLS_KINDS = (
    ("nfp", "非农就业报告", "Employment Situation"),
    ("cpi", "CPI 数据公布", "Consumer Price Index"),
)


def parse_bls_events(html: str) -> list[MacroEvent]:
    """解析 BLS 新版月度日历页（2026 起改版）。

    结构：<td id="dMMDD"> 单元格内 <p class="day">日期</p> 与
    <p><strong>事件名</strong> 数据期<br> 时间</p> 事件块；页面标题
    "Schedule of Selected Releases for August 2026" 提供年份，跨月格
    （上月/下月）按相对页面月归属年份。
    """
    title_match = re.search(r"for (\w+) (\d{4})", html)
    if title_match is None:
        return []
    page_year = int(title_match.group(2))
    try:
        page_month = datetime.strptime(title_match.group(1), "%B").month
    except ValueError:
        return []
    events: list[MacroEvent] = []
    for month_day, cell_html in _BLS_CELL_PATTERN.findall(html):
        mm, dd = int(month_day[:2]), int(month_day[2:])
        year = _bls_cell_year(page_year, page_month, mm)
        if year is None:
            continue
        for block in re.findall(r"<p>(.*?)</p>", cell_html, flags=re.DOTALL):
            strong = " ".join(
                " ".join(re.sub(r"<[^>]+>", " ", match).split())
                for match in re.findall(
                    r"<strong>(.*?)</strong>", block, flags=re.DOTALL
                )
            )
            kind_title = _bls_kind(strong)
            if kind_title is None:
                continue
            kind, title = kind_title
            hour, minute = _bls_time(block)
            try:
                event_date = date(year, mm, dd)
            except ValueError:
                # 畸形日期（如 2 月 30 日）跳过，整体不抛异常
                continue
            events.append(_event(kind, title, event_date, hour, minute, "bls"))
    return events


def _bls_cell_year(
    page_year: int, page_month: int, cell_month: int
) -> int | None:
    """单元格月份归属年份：日历只含上月尾部、当月、下月头部。

    相邻月与页面月同年；仅跨年场景（1 月页含去年 12 月、
    12 月页含明年 1 月）年份偏移。
    """
    if page_month == 1 and cell_month == 12:
        return page_year - 1
    if page_month == 12 and cell_month == 1:
        return page_year + 1
    if cell_month in (page_month - 1, page_month, page_month + 1):
        return page_year
    return None


def _bls_kind(strong: str) -> tuple[str, str] | None:
    for kind, title, marker in _BLS_KINDS:
        if marker in strong:
            return kind, title
    return None


def _bls_time(block: str) -> tuple[int, int]:
    """事件块内的发布时间（AM/PM → 24h）；缺失时按 08:30 兜底。"""
    time_match = _BLS_TIME_PATTERN.search(block)
    if time_match is None:
        return 8, 30
    hour, minute = int(time_match.group(1)), int(time_match.group(2))
    if time_match.group(3) == "PM" and hour < 12:
        hour += 12
    if time_match.group(3) == "AM" and hour == 12:
        hour = 0
    return hour, minute


def _bls_page_url(year: int, month: int) -> str:
    """BLS 月度排期页 URL（如 2026 年 8 月：/schedule/2026/08_sched.htm）。"""
    return f"https://www.bls.gov/schedule/{year}/{month:02d}_sched.htm"


def _bls_pages(start: date) -> list[tuple[int, int]]:
    """窗口起始月起连抓当月与下月两个日历页（跨月事件不会遗漏）。"""
    next_year, next_month = (
        (start.year + 1, 1) if start.month == 12 else (start.year, start.month + 1)
    )
    return [(start.year, start.month), (next_year, next_month)]


def _fetch_bls_events(client: httpx.Client, start: date) -> list[MacroEvent] | None:
    """抓取当月与下月 BLS 日历页并合并解析；任一页失败整体视为 BLS 不可用。"""
    events: list[MacroEvent] = []
    for page_year, page_month in _bls_pages(start):
        response = _get_with_redirect(client, _bls_page_url(page_year, page_month))
        response.raise_for_status()
        events.extend(parse_bls_events(response.text))
    # 相邻两页的 other-month 格可能重复同一事件（如 9/4 非农），按 kind+时间去重
    deduped: dict[tuple[str, datetime], MacroEvent] = {}
    for event in events:
        deduped.setdefault((event.kind, event.event_at), event)
    return list(deduped.values())


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

