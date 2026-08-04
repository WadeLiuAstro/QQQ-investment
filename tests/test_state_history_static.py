from pathlib import Path


def test_state_history_dom_contract_and_styles() -> None:
    page = Path("static/index.html").read_text(encoding="utf-8")
    script = Path("static/assets/app.js").read_text(encoding="utf-8")
    styles = Path("static/assets/style.css").read_text(encoding="utf-8")

    assert "id=\"state-history\"" in page

    assert "renderStateHistory" in script
    assert "state-history" in script
    assert "state_history" in script  # 旧快照回退判断
    assert "切换" in script
    assert "已持续" in script
    assert "暂无状态切换记录" in script
    assert "定投倍率" in script

    assert ".timeline" in styles
    assert "@media(max-width:640px)" in styles and "state-history" in styles
