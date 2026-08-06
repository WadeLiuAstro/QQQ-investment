"""Task 4/5: monitoring 前端静态契约测试（容器位置/可访问性/渲染函数/响应式）。"""

from pathlib import Path

HTML = Path("static/index.html")
SCRIPT = Path("static/assets/app.js")
CSS = Path("static/assets/style.css")


# --- Task 4: 容器与手风琴骨架 ---

def test_monitoring_container_follows_core_hero() -> None:
    html = HTML.read_text(encoding="utf-8")
    assert html.index('class="grid hero"') < html.index('id="monitoring-section"')
    assert html.index('id="monitoring-section"') < html.index('id="event-list"')
    assert 'id="monitoring-summary"' in html
    assert 'id="monitoring-groups"' in html
    assert "监控佐证层" in html


def test_monitoring_accordion_is_accessible() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert "aria-expanded" in script
    assert "aria-controls" in script
    assert "sessionStorage" in script
    assert "monitoring-open-group" in script


def test_monitoring_core_renderers_exist() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    for name in (
        "renderMonitoring",
        "renderMonitoringSummary",
        "renderMonitoringGroups",
        "setOpenMonitoringGroup",
        "toggleMonitoringGroup",
    ):
        assert f"function {name}" in script
    assert "renderMonitoring(p.monitoring)" in script


def test_monitoring_hidden_when_payload_absent() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert "hidden=true" in script
    assert "if(!m)" in script


# --- Task 5: 展开可视化渲染函数与样式 ---

def test_monitoring_detail_renderers_exist() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    for name in (
        "renderSentimentVolatility",
        "renderCoreBreadth",
        "renderSectorRotation",
        "renderMacroDefensive",
        "renderMonitoringMetricRow",
    ):
        assert f"function {name}" in script
    assert "CNN 七项分因子" in script
    assert "部分数据缺失" in script


def test_monitoring_responsive_and_isolated_styles() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert ".monitoring-summary" in css
    assert ".monitoring-group" in css
    assert ".monitoring-factor-track" in css
    assert "@media" in css
    assert "grid-template-columns:repeat(2" in css


def test_monitoring_does_not_depend_on_hover_only() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    # 分组按钮使用原生 button（键盘 Enter/Space），而非 hover 触发
    assert 'type="button"' in script


# --- 情绪指数仪表盘组件（F&G 五档 + 历史对比）---


def test_sentiment_gauge_component_contract() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    for name in (
        "renderSentimentGauge",
        "renderSentimentComparisons",
        "renderMonitoringTableHeader",
        "fgStatusColor",
    ):
        assert f"function {name}" in script
    assert "FG_BANDS" in script  # 五段色带
    assert "综合判断：当前美国市场情绪为" in script
    assert "<svg" in script  # gauge 用 SVG 渲染


def test_sentiment_gauge_styles_present() -> None:
    css = CSS.read_text(encoding="utf-8")
    for cls in (".fg-gauge", ".fg-needle", ".fg-verdict", ".fg-comparisons", ".fg-comp-card", ".monitoring-row-head"):
        assert cls in css


def test_backend_five_tier_thresholds_match_frontend_bands() -> None:
    from app.services.monitoring import _cnn_status

    # 与前端 FG_BANDS 区间一致：0-25/25-45/45-55/55-75/75-100
    assert _cnn_status(10) == "恐惧"
    assert _cnn_status(30) == "谨慎"
    assert _cnn_status(50) == "中性"
    assert _cnn_status(60) == "乐观"
    assert _cnn_status(90) == "贪婪"


def test_global_scrollbar_matches_dark_theme() -> None:
    css = CSS.read_text(encoding="utf-8")
    # 批注修复：横向滚动条（如 threshold-wrap）使用与暗色主题一致的细滚动条
    assert "::-webkit-scrollbar" in css
    assert "scrollbar-width:thin" in css


def test_monitoring_vol_rows_have_table_header() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    # VIX/VIX3M/VIX-VIX3M 等资产行上方有表头标注，提升可读性
    assert "renderMonitoringTableHeader" in script
    assert "资产" in script and "最新值" in script and "5日方向" in script


# --- 近一年市场情绪走势图 ---


def test_sentiment_history_chart_contract() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert "function renderSentimentHistoryChart" in script
    assert "近一年市场情绪走势" in script
    # 降级文案：CNN 历史不可用时明确提示，不伪造数据
    assert "暂无历史走势数据" in script
    # 数据来自 monitoring details.history（CNN graphdata），悬停展示日期/分数/标签
    assert "d.history" in script
    assert "fg-history-readout" in script


def test_sentiment_history_chart_styles_present() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert ".fg-history" in css
    assert ".fg-history-readout" in css


def test_sentiment_history_chart_inserted_before_factors() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    # 走势图位于四张情绪对比卡之后、CNN 七项分因子之前
    render = script[script.index("function renderSentimentVolatility"):]
    comps_pos = render.index("compsHtml")
    history_pos = render.index("renderSentimentHistoryChart(")
    factors_pos = render.index("factorHtml")
    assert comps_pos < history_pos < factors_pos


def test_frontend_fg_bands_match_backend_five_tiers() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    # 走势图分档线与 gauge 色带共用 FG_BANDS，区间必须与后端 _cnn_status 一致
    for boundary in (
        "{from:0,to:25",
        "{from:25,to:45",
        "{from:45,to:55",
        "{from:55,to:75",
        "{from:75,to:100",
    ):
        assert boundary in script, f"FG_BANDS 缺少与后端一致的分档 {boundary}"


def test_sentiment_gauge_center_text_does_not_overlap_needle() -> None:
    css = CSS.read_text(encoding="utf-8")
    # 批注修复：中心数值不再绝对定位叠在指针/表盘轴上，改为表盘下方正常流布局
    assert ".fg-gauge-center{position:absolute" not in css.replace(" ", "")
