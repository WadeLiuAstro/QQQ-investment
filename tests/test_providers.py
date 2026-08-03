from datetime import UTC, datetime

import httpx

from app.providers.cnn_fear_greed import fetch_fear_greed


def test_fear_greed_maps_current_score() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "fear_and_greed": {
                    "score": 39,
                    "rating": "fear",
                    "timestamp": "2026-08-03T15:45:00Z",
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reading, status = fetch_fear_greed(client)

    assert reading.score == 39
    assert reading.rating == "fear"
    assert reading.observed_at == datetime(2026, 8, 3, 15, 45, tzinfo=UTC)
    assert status.available is True


def test_fear_greed_failure_returns_unavailable_status() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reading, status = fetch_fear_greed(client)

    assert reading is None
    assert status.available is False
    assert status.source == "cnn_fear_greed"
