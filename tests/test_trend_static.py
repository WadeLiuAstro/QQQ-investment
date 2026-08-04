"""S1d: 前端静态契约测试——趋势层与结构性风险评分面板。"""

from pathlib import Path


def test_trend_and_structural_panel_contract() -> None:
    html = Path("static/index.html").read_text(encoding="utf-8")
    script = Path("static/assets/app.js").read_text(encoding="utf-8")
    css = Path("static/assets/style.css").read_text(encoding="utf-8")

    # DOM 契约
    assert 'id="trend-card"' in html
    assert 'id="structural-card"' in html
    assert "体系趋势层" in html
    assert "结构性风险评分" in html

    # 渲染函数与数据接入
    assert "function renderTrend" in script
    assert "function renderStructural" in script
    assert "renderTrend(q.trend)" in script
    assert "renderStructural(q.structural_risk)" in script

    # 判读档位文案
    assert "疑似结构性" in script
    assert "≥70 冻结加仓" in script
    assert "40–69 减半" in script

    # 样式
    assert ".structural-dims" in css
    assert ".dim-item" in css
