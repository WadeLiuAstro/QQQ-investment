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


def test_news_event_and_headline_row_structure() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    for cls in ("news-event", "ne-title", "ne-date", "ne-days", "news-item", "ni-time", "ni-src", "ni-title", "ni-link"):
        assert cls in script
    assert "临近 · " in script
    assert " 天后" in script


# --- 样式契约 ---

def test_news_styles_responsive() -> None:
    css = CSS.read_text(encoding="utf-8")
    for cls in ("#news-section", ".news-upcoming", ".news-event", ".ne-days.near", ".news-item", ".ni-src", ".news-footnote"):
        assert cls in css, f"style.css 缺少 {cls}"
    assert "@media" in css


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
