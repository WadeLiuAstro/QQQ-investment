from pathlib import Path


def test_action_card_dom_contract_and_styles() -> None:
    page = Path("static/index.html").read_text(encoding="utf-8")
    script = Path("static/assets/app.js").read_text(encoding="utf-8")
    styles = Path("static/assets/style.css").read_text(encoding="utf-8")

    assert "id=\"extra-topup\"" in page
    assert "id=\"completeness\"" in page
    assert "id=\"watch-conditions\"" in page

    assert "renderActionCard" in script
    assert "extra-topup" in script
    assert "completeness" in script
    assert "watch-conditions" in script
    assert "额外加仓" in script
    assert "数据完整度" in script
    assert "观察条件" in script
    assert "已满足" in script and "观察中" in script
    assert "action_card" in script  # 旧快照回退判断

    assert ".chip" in styles
    assert ".watch" in styles
    assert "@media(max-width:640px)" in styles and "watch-conditions" in styles
