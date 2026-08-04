from pathlib import Path


def test_breadth_card_dom_contract_and_styles() -> None:
    page = Path("static/index.html").read_text(encoding="utf-8")
    script = Path("static/assets/app.js").read_text(encoding="utf-8")
    styles = Path("static/assets/style.css").read_text(encoding="utf-8")

    assert "id=\"breadth-card\"" in page

    assert "renderBreadth" in script
    assert "breadth" in script  # 旧快照回退判断
    assert "市场宽度" in script
    assert "集中度" in script
    assert "等权" in script
    assert "相对强弱" in script
    assert "未参与" in script

    assert ".breadth" in styles
    assert "@media(max-width:640px)" in styles and "breadth" in styles
