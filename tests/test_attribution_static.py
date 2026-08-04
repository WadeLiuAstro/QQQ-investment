"""S2d: 前端静态契约测试——大跌归因卡片与决策日志。"""

from pathlib import Path


def test_attribution_panel_contract() -> None:
    html = Path("static/index.html").read_text(encoding="utf-8")
    script = Path("static/assets/app.js").read_text(encoding="utf-8")
    css = Path("static/assets/style.css").read_text(encoding="utf-8")

    # DOM 契约
    assert 'id="attribution-card"' in html
    assert 'id="decision-log-card"' in html
    assert "机器举证" in html

    # 渲染与交互
    assert "function renderAttribution" in script
    assert "renderAttribution(q.attribution)" in script
    assert "function renderDecisionLog" in script
    assert "loadDecisionLog" in script
    assert "api/attribution" in script  # 拍板提交端点
    assert "api/decision-log" in script  # 日志端点
    assert "导出 JSON（静态站降级）" in script
    assert "静态站模式" in script

    # 三分类文案与超时语义
    assert "流动性恐慌" in script
    assert "结构性风险" in script
    assert "待观察" in script
    assert "48h 复核" in script

    # 样式
    assert ".attribution-form" in css
