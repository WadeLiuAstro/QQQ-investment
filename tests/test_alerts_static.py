from pathlib import Path


def test_alert_banner_dom_contract_and_styles() -> None:
    page = Path("static/index.html").read_text(encoding="utf-8")
    script = Path("static/assets/app.js").read_text(encoding="utf-8")
    styles = Path("static/assets/style.css").read_text(encoding="utf-8")

    assert "id=\"alert-banner\"" in page

    assert "renderAlerts" in script
    assert "alert-banner" in script
    assert "alerts" in script  # 空列表/缺失隐藏判断
    assert "仅页面内提醒" in script and "不推送" in script
    assert "状态切换" in script
    assert "持续不可用" in script
    assert "临近" in script

    assert ".alert" in styles
    assert "@media(max-width:640px)" in styles and "alert" in styles
