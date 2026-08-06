"""scripts/refresh_dashboard.py 双模式刷新脚本测试。"""

import scripts.refresh_dashboard as script


def test_resolve_action_auto_uses_guard_when_session_open() -> None:
    assert script.resolve_action("auto", session_open=True) == "guard"


def test_resolve_action_auto_uses_daily_when_session_closed() -> None:
    assert script.resolve_action("auto", session_open=False) == "daily"


def test_resolve_action_daily_always_daily() -> None:
    assert script.resolve_action("daily", session_open=True) == "daily"
    assert script.resolve_action("daily", session_open=False) == "daily"


def test_resolve_action_guard_always_guard() -> None:
    assert script.resolve_action("guard", session_open=True) == "guard"
    assert script.resolve_action("guard", session_open=False) == "guard"


def _stub_dependencies(monkeypatch, session_open: bool, calls: dict) -> None:
    """替换脚本依赖，避免真实抓取与写库。"""
    monkeypatch.setattr(script, "SnapshotRepository", lambda path: "repo")
    monkeypatch.setattr(script, "is_regular_session_open", lambda: session_open)
    monkeypatch.setattr(
        script,
        "refresh_once",
        lambda repository, export_path: calls.update(
            daily=(repository, export_path)
        ),
    )
    monkeypatch.setattr(
        script,
        "run_intraday_guard",
        lambda repository, export_path: calls.update(
            guard=(repository, export_path)
        ),
    )


def test_main_daily_mode_calls_refresh_once(monkeypatch) -> None:
    calls: dict = {}
    _stub_dependencies(monkeypatch, session_open=True, calls=calls)

    script.main(["--mode", "daily"])

    assert "daily" in calls
    assert "guard" not in calls
    assert calls["daily"] == ("repo", script.EXPORT_PATH)


def test_main_guard_mode_calls_run_intraday_guard(monkeypatch) -> None:
    calls: dict = {}
    _stub_dependencies(monkeypatch, session_open=False, calls=calls)

    script.main(["--mode", "guard"])

    assert "guard" in calls
    assert "daily" not in calls
    assert calls["guard"] == ("repo", script.EXPORT_PATH)


def test_main_auto_mode_uses_guard_during_session(monkeypatch) -> None:
    calls: dict = {}
    _stub_dependencies(monkeypatch, session_open=True, calls=calls)

    script.main(["--mode", "auto"])

    assert "guard" in calls
    assert "daily" not in calls


def test_main_auto_mode_uses_daily_outside_session(monkeypatch) -> None:
    calls: dict = {}
    _stub_dependencies(monkeypatch, session_open=False, calls=calls)

    script.main(["--mode", "auto"])

    assert "daily" in calls
    assert "guard" not in calls


def test_main_defaults_to_auto_mode(monkeypatch) -> None:
    calls: dict = {}
    _stub_dependencies(monkeypatch, session_open=True, calls=calls)

    script.main([])

    assert "guard" in calls
    assert "daily" not in calls
