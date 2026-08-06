"""Task D: 消息面卡片（样本 C：预期事件 + 头条混排）前端静态契约测试。"""

from pathlib import Path

HTML = Path("static/index.html")
SCRIPT = Path("static/assets/app.js")
CSS = Path("static/assets/style.css")


# --- 容器位置与结构 ---

def test_news_section_follows_monitoring() -> None:
    html = HTML.read_text(encoding="utf-8")
    assert 'id="news-section"' in html
    # 消息面卡片位于 monitoring-section 之后
    assert html.index('id="monitoring-section"') < html.index('id="news-section"')
    assert "消息面 · 预期与头条" in html
    for id_ in (
        'id="news-updated"',
        'id="news-upcoming"',
        'id="news-section-title"',
        'id="news-headlines"',
        'id="news-footnote"',
    ):
        assert id_ in html


# --- 渲染函数与降级文案契约 ---

def test_news_render_function_contract() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert "function renderNewsCard" in script
    assert "消息面 · 预期与头条" in script
    assert "新闻源暂不可用，仅展示排期事件" in script
    assert "近三日暂无收录头条" in script
    assert "随日频快照更新" in script
    assert 'target="_blank"' in script
    assert 'rel="noopener"' in script
    assert "renderNewsCard(p.news" in script


def test_news_hidden_when_payload_absent() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    render = script[script.index("function renderNewsCard"):script.index("function renderAttribution")]
    assert "if(!n)" in render
    assert "hidden=true" in render
    assert "消息面暂不可用" in render
    assert "暂无排期事件" in render


def test_news_external_fields_escaped() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    # title/source/url 来自外部数据，拼接前做最小 HTML 转义
    assert ".replace(/&/g,'&amp;')" in script
    assert ".replace(/</g,'&lt;')" in script
    assert ".replace(/>/g,'&gt;')" in script


def test_news_headline_row_structure() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    for cls in ("news-item", "ni-time", "ni-src", "ni-title", "ni-link"):
        assert cls in script


# --- Task B：月历视图契约 ---

def test_news_calendar_contract() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert "function renderNewsCalendar" in script
    assert "下月事件" in script
    assert "点按事件日查看详情" in script
    assert "news-cal-readout" in script
    assert "aria-label" in script
    # 周一起始表头：拆成 7 个 span，与下方 7 列日历逐列对齐
    assert '<div class="nc-head"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div>' in script


def test_news_card_no_longer_renders_event_cards() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    render = script[script.index("function renderNewsCard"):script.index("function renderAttribution")]
    # renderNewsCard 内不再渲染旧事件卡结构
    assert "news-event" not in render
    assert "renderNewsCalendar(upcoming)" in render
    # 降级路径保留
    assert "暂无排期事件" in render


def test_news_calendar_styles() -> None:
    css = CSS.read_text(encoding="utf-8")
    for cls in (".news-calendar", ".nc-day.near", ".nc-day.has-event", ".nc-day:focus-visible", ".nc-next-month", "#news-cal-readout"):
        assert cls in css, f"style.css 缺少 {cls}"
    # 全局 button 悬浮规则（right/bottom 定位）不得泄漏到日历事件按钮
    assert ".nc-day{position:relative;right:auto;bottom:auto" in css


def test_news_calendar_day_tooltip_contract() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    # 事件日同时带原生 title 与 data-titles（悬停浮层数据源）
    assert 'title="${ds} ${titles}"' in script
    assert 'data-titles="${titles}"' in script
    css = CSS.read_text(encoding="utf-8")
    # 悬停浮层仅在真实悬停设备生效，移动端不受影响
    assert "@media(hover:hover)" in css
    assert ".nc-day.has-event::after" in css
    assert "attr(data-titles)" in css


def test_event_list_summary_contract() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    # 未来七日事件卡改为摘要式：中文标题、北京时间含星期、来源、静态背景说明
    for token in (
        "function renderEventList",
        "renderEventList(p.events)",
        "非农就业报告",
        "CPI 通胀数据",
        "FOMC 利率决议",
        "美国劳工统计局",
        "美联储",
        "北京时间",
        "eventKindContext",
    ):
        assert token in script, f"app.js 缺少 {token}"
    # 北京时间显式按 UTC+8 换算，不依赖访客本地时区
    assert "8*3600000" in script
    css = CSS.read_text(encoding="utf-8")
    for cls in (".event-item", ".event-title", ".event-time", ".event-src", ".event-context"):
        assert cls in css, f"style.css 缺少 {cls}"


# --- 样式契约 ---

def test_news_styles_responsive() -> None:
    css = CSS.read_text(encoding="utf-8")
    for cls in ("#news-section", ".news-upcoming", ".news-event", ".ne-days.near", ".news-item", ".ni-src", ".news-footnote"):
        assert cls in css, f"style.css 缺少 {cls}"
    assert "@media" in css


# --- Task C：顶部头条摘要栏契约 ---

def test_news_topbar_html_contract() -> None:
    html = HTML.read_text(encoding="utf-8")
    assert 'id="news-ticker-bar"' in html
    assert 'tabindex="0"' in html
    # 位于信号带之后、main 其余内容（alert-banner）之前
    assert html.index('class="signal-band"') < html.index('id="news-ticker-bar"')
    assert html.index('id="news-ticker-bar"') < html.index('id="alert-banner"')
    assert 'id="nt-label"' in html
    assert 'id="nt-stage"' in html


def test_news_topbar_script_contract() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    for token in (
        "function renderNewsTopbar",
        "消息面 · 日频更新",
        "setInterval",
        "8000",
        "prefers-reduced-motion",
        "scrollIntoView",
        "news-section",
        "mouseenter",
        "focusin",
        "mouseleave",
        "focusout",
        "Enter",
        "newsEscapeHtml",
    ):
        assert token in script, f"app.js 缺少 {token}"
    # renderDashboard 中以 headlines + generated_at 调用
    assert "renderNewsTopbar((p.news||{}).headlines||[],p.generated_at)" in script


def test_news_topbar_no_third_party_marquee() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert "marquee" not in script.lower()


def test_news_topbar_styles() -> None:
    css = CSS.read_text(encoding="utf-8")
    for cls in (".news-ticker", ".nt-label", ".nt-stage", ".nt-item", ".nt-item.active", ".news-ticker:focus-visible"):
        assert cls in css, f"style.css 缺少 {cls}"
    assert "opacity" in css
    assert "grid-area:1/1" in css


# --- 调用顺序与决策隔离 ---

def test_news_called_after_monitoring_in_render_dashboard() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    render = script[script.index("function renderDashboard"):]
    assert render.index("renderMonitoring(p.monitoring)") < render.index("renderNewsCard(p.news")


def test_decision_rendering_isolated() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    render = script[script.index("function renderDashboard"):]
    # 决策/状态渲染片段未被改动
    assert "'#state').textContent=d?.state" in render
