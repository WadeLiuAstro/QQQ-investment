import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_scenario_panel_dom_contract_and_styles() -> None:
    page = read("static/index.html")
    script = read("static/assets/app.js")
    styles = read("static/assets/style.css")

    assert "id=\"scenario-panel\"" in page
    assert "id=\"scenario-result\"" in page
    assert "id=\"simulate-button\"" in page
    assert "id=\"sim-reset-button\"" in page
    for field in ("sim-price", "sim-rsi2", "sim-rsi6", "sim-drawdown", "sim-vix", "sim-volume"):
        assert f"id=\"{field}\"" in page

    assert "simulateScenario" in script
    assert "SIM_THRESHOLDS" in script
    assert "模拟结果" in script and "不是当前实时信号" in script
    assert "sim-reset-button" in script
    assert "加仓机会" in script

    assert ".sim" in styles
    assert "@media(max-width:640px)" in styles and "scenario" in styles


def test_simulator_thresholds_match_default_rules() -> None:
    rules = json.loads(read("config/default_rules.json"))
    script = read("static/assets/app.js")

    thresholds = rules["thresholds"]
    expected = {
        "rsi2_oversold": thresholds["rsi2_oversold"],
        "rsi6_oversold": thresholds["rsi6_oversold"],
        "vix_high": thresholds["vix_high"],
        "drawdown_risk": thresholds["drawdown_risk"],
    }
    for key, value in expected.items():
        assert f"{key}:{value:g}" in script, f"SIM_THRESHOLDS 缺少与规则一致的 {key}={value:g}"
