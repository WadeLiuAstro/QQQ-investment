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


def test_fear_greed_request_sends_browser_headers() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.headers)
        return httpx.Response(
            200,
            json={
                "fear_and_greed": {
                    "score": 45,
                    "rating": "neutral",
                    "timestamp": "2026-08-04T00:00:00Z",
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reading, status = fetch_fear_greed(client)

    assert status.available is True
    assert captured.get("user-agent", "").startswith("Mozilla/5.0")
    assert "referer" in captured
    assert "cnn.com" in captured.get("referer", "")


def _full_payload() -> dict:
    return {
        "fear_and_greed": {
            "score": 58.4,
            "rating": "greed",
            "timestamp": "2026-08-04T20:00:00+00:00",
            "previous_close": 46.0,
            "previous_1_week": 38.0,
            "previous_1_month": 33.0,
            "previous_1_year": 64.0,
        },
        "fear_and_greed_historical": {
            "data": [[1785800000000, 46.0], [1785886400000, 58.4]]
        },
        "market_momentum_sp500": {"score": 81.0, "rating": "extreme greed"},
        "stock_price_strength": {"score": 45.0, "rating": "neutral"},
        "stock_price_breadth": {"score": 60.0, "rating": "greed"},
        "put_call_options": {"score": 50.0, "rating": "neutral"},
        "market_volatility_vix": {"score": 66.0, "rating": "greed"},
        "junk_bond_demand": {"score": 55.0, "rating": "greed"},
        "safe_haven_demand": {"score": 40.0, "rating": "fear"},
    }


def test_fear_greed_parses_optional_monitoring_details() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_full_payload())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reading, status = fetch_fear_greed(client)

    assert status.available is True
    assert reading.score == 58
    assert reading.previous_close == 46.0
    assert reading.previous_week == 38.0
    assert reading.previous_month == 33.0
    assert reading.previous_year == 64.0
    assert len(reading.history) == 2
    assert reading.history[-1].score == 58.4
    assert len(reading.factors) == 7
    assert reading.factors[0].key == "market_momentum"
    assert reading.factors[0].label == "市场动量"
    assert reading.factors[0].score == 81.0


def test_fear_greed_current_only_has_empty_optionals() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "fear_and_greed": {
                    "score": 42,
                    "rating": "fear",
                    "timestamp": "2026-08-04T00:00:00Z",
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reading, status = fetch_fear_greed(client)

    assert status.available is True
    assert reading.score == 42
    assert reading.previous_close is None
    assert reading.history == ()
    assert reading.factors == ()


def test_fear_greed_http_418_returns_unavailable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(418, text="I'm a teapot. You're a bot.")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reading, status = fetch_fear_greed(client)

    assert reading is None
    assert status.available is False


def test_fear_greed_malformed_required_current_returns_unavailable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"fear_and_greed": {"rating": "fear"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reading, status = fetch_fear_greed(client)

    assert reading is None
    assert status.available is False


def test_fear_greed_skips_malformed_optional_fields_independently() -> None:
    payload = _full_payload()
    payload["fear_and_greed_historical"] = {"data": [["not-a-timestamp", "bad"]]}
    payload["market_momentum_sp500"] = {"score": "invalid"}

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reading, status = fetch_fear_greed(client)

    assert status.available is True
    assert reading.score == 58  # required score still parsed
    assert reading.history == ()  # malformed history skipped
    assert all(factor.key != "market_momentum" for factor in reading.factors)
    assert len(reading.factors) == 6  # only malformed factor skipped


def test_fear_greed_history_accepts_xy_object_shape() -> None:
    payload = _full_payload()
    payload["fear_and_greed_historical"] = {
        "data": [{"x": 1785800000000, "y": 46.0}, {"x": 1785886400000, "y": 58.4}]
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reading, _ = fetch_fear_greed(client)

    assert len(reading.history) == 2
    assert reading.history[-1].score == 58.4
