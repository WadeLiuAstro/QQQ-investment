from datetime import date

import httpx

from app.providers.macro_calendar import load_macro_events, parse_fomc_events

# Fed 页面新结构 fixture：
# - 年份分段标题为 <h4><a id="数字">YYYY FOMC Meetings</a></h4>
# - 月份在 fomc-meeting__month 块的 <strong> 内，日期在其后独立的 fomc-meeting__date 块内
# - 日期形如 "起始日-结束日"，可能带 * 号；会议日期语义取结束日
NEW_FED_HTML = """
<h4><a id="42500">2025 FOMC Meetings</a></h4>
<div class="col-xs-12 col-sm-4 fomc-meeting">
  <div class="fomc-meeting__month"><strong>November</strong></div>
  <div class="fomc-meeting__date ">6-7</div>
</div>
<div class="col-xs-12 col-sm-4 fomc-meeting">
  <div class="fomc-meeting__month"><strong>December</strong></div>
  <div class="fomc-meeting__date ">9-10</div>
</div>
<h4><a id="42828">2026 FOMC Meetings</a></h4>
<div class="col-xs-12 col-sm-4 fomc-meeting">
  <div class="fomc-meeting__month"><strong>January</strong></div>
  <div class="fomc-meeting__date ">27-28</div>
</div>
<div class="col-xs-12 col-sm-4 fomc-meeting">
  <div class="fomc-meeting__month"><strong>September</strong></div>
  <div class="fomc-meeting__date ">15-16*</div>
  <div class="fomc-meeting__links"><a href="#">agenda</a></div>
</div>
"""

BLS_HTML = """
    <table>
      <tr><td>Employment Situation</td><td>Friday, September 4, 2026</td></tr>
      <tr><td>Consumer Price Index</td><td>Friday, September 11, 2026</td></tr>
    </table>
    """


def test_parse_fomc_events_new_structure() -> None:
    # 新结构：年份分段 + 月份/日期分块；会议日期取范围结束日
    events = parse_fomc_events(NEW_FED_HTML)

    assert [event.event_at.date() for event in events] == [
        date(2025, 11, 7),
        date(2025, 12, 10),
        date(2026, 1, 28),
        date(2026, 9, 16),
    ]
    for event in events:
        assert event.kind == "fomc"
        assert event.title == "FOMC 利率决议"
        assert event.source == "federal_reserve"
        assert event.event_at.hour == 14
        assert event.event_at.minute == 0


def test_parse_fomc_events_year_attribution_no_cross_year_mispair() -> None:
    # 跨年不误配：2025 段的 December 会议必须归属 2025 而非 2026
    events = parse_fomc_events(NEW_FED_HTML)
    december_events = [
        event for event in events if event.event_at.month == 12
    ]
    assert [event.event_at.date() for event in december_events] == [
        date(2025, 12, 10)
    ]


def test_parse_fomc_events_skips_malformed_blocks() -> None:
    # 畸形片段（有 strong 月份但其后无日期块）被跳过且不抛异常
    malformed_html = """
    <h4><a id="1">2026 FOMC Meetings</a></h4>
    <div class="fomc-meeting__month"><strong>March</strong></div>
    <div class="fomc-meeting__month"><strong>April</strong></div>
    <div class="fomc-meeting__date ">28-29</div>
    """
    events = parse_fomc_events(malformed_html)
    assert [event.event_at.date() for event in events] == [date(2026, 4, 29)]


def test_parse_fomc_events_ignores_month_strong_without_meeting_class() -> None:
    # 年份段内不带 fomc-meeting__month 类的 <strong>月份</strong> 干扰文本
    # （如纪要/新闻措辞）不得被误配为会议
    noisy_html = """
    <h4><a id="1">2026 FOMC Meetings</a></h4>
    <div class="col-xs-12 col-sm-4 fomc-meeting">
      <div class="fomc-meeting__month"><strong>January</strong></div>
      <div class="fomc-meeting__date ">27-28</div>
    </div>
    <p>The <strong>March</strong> minutes will be published later.</p>
    <div class="fomc-meeting__date ">17-18</div>
    <div class="col-xs-12 col-sm-4 fomc-meeting">
      <div class="fomc-meeting__month "><span><strong>September</strong></span></div>
      <div class="fomc-meeting__date ">15-16</div>
    </div>
    """
    events = parse_fomc_events(noisy_html)

    # 干扰的 <strong>March</strong> 不产生会议；类名锚定的月份正常解析
    # （September 容忍类属性尾部空白与 div/strong 之间的 HTML 噪声）
    assert [(event.event_at.date()) for event in events] == [
        date(2026, 1, 28),
        date(2026, 9, 16),
    ]


def test_parse_fomc_events_unknown_structure_returns_empty() -> None:
    # 页面结构无法识别时返回空列表，由调用方降级，绝不抛异常
    assert parse_fomc_events("<html>September 15-16, 2026</html>") == []
    assert parse_fomc_events("") == []


def test_macro_calendar_loads_fomc_cpi_and_employment_events() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "federalreserve" in str(request.url):
            return httpx.Response(200, text=NEW_FED_HTML)
        return httpx.Response(200, text=BLS_HTML)

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


def test_macro_calendar_bls_blocked_keeps_fomc_events() -> None:
    # BLS 被反爬封锁（403）时，FOMC 事件仍应正常返回
    def handler(request: httpx.Request) -> httpx.Response:
        if "federalreserve" in str(request.url):
            return httpx.Response(200, text=NEW_FED_HTML)
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
