from app.providers.yahoo import fetch_daily_bars


def test_yahoo_download_failure_returns_unavailable_status() -> None:
    def failing_download(**_: object) -> object:
        raise RuntimeError("provider unavailable")

    bars, status = fetch_daily_bars("QQQ", "1y", downloader=failing_download)

    assert bars is None
    assert status.available is False
    assert status.source == "yahoo"

def test_yahoo_download_requests_unadjusted_closes() -> None:
    captured: dict[str, object] = {}

    def downloader(*_: object, **kwargs: object) -> object:
        captured.update(kwargs)
        raise RuntimeError("stop after request inspection")

    fetch_daily_bars("QQQ", "1y", downloader=downloader)

    assert captured["auto_adjust"] is False

