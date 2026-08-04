from pathlib import Path


def test_threshold_matrix_dom_contract_and_styles() -> None:
    script = Path("static/assets/app.js").read_text(encoding="utf-8")
    styles = Path("static/assets/style.css").read_text(encoding="utf-8")

    assert "renderThresholdMatrix" in script
    assert "threshold-matrix" in script
    assert "近 5 日方向" in script and "触发条件" in script
    assert "未参与本次判断" in script
    assert "扩大" in script and "收窄" in script
    assert ".threshold-matrix" in styles
    assert "@media(max-width:640px)" in styles and "threshold-matrix" in styles
