"""Task D: 日频快照语义展示与熔断预警提醒类型前端静态契约测试。"""

from pathlib import Path

SCRIPT = Path("static/assets/app.js")
CSS = Path("static/assets/style.css")


def test_alert_kind_names_include_circuit_breaker() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert "circuit_breaker:'熔断预警'" in script


def test_snapshot_semantics_strings_present() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    for text in (
        "日频正式快照",
        "生成于",
        "盘中守护",
        "已触发熔断预警",
        "intraday_watch",
        "snapshot_kind",
    ):
        assert text in script, f"app.js 缺少快照语义文案/字段 {text}"


def test_snapshot_note_style_present() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert ".snapshot-note" in css


def test_decision_rendering_not_touched() -> None:
    # 决策隔离断言：状态/仓位/定投倍率的渲染语句保持原样
    script = SCRIPT.read_text(encoding="utf-8")
    for fragment in (
        "'#state').textContent=d?.state",
        "'#allocation').textContent=d?",
        "'#dca').textContent=d?",
    ):
        assert fragment in script, f"决策渲染语句被改动：{fragment}"
