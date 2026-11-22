from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from voltia.sources.openmeteo import FORECAST_URL, OpenMeteoClient


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waited: list[float] = []
    monkeypatch.setattr(OpenMeteoClient._get.retry, "sleep", waited.append)  # type: ignore[attr-defined]
    return waited


@respx.mock
def test_a_minute_of_503_does_not_lose_the_day(
    sleeps: list[float], load_json: Callable[[str], Any]
) -> None:
    payload = load_json("other/openmeteo_two_cities.json")
    route = respx.get(FORECAST_URL).mock(
        side_effect=[*[httpx.Response(503)] * 5, httpx.Response(200, json=payload)]
    )
    assert OpenMeteoClient()._get(FORECAST_URL, {}) == payload
    assert route.call_count == 6
    assert sleeps == [2, 4, 8, 16, 32]  # about a minute in all


@respx.mock
def test_a_longer_outage_still_fails_and_leaves_the_retry_to_the_next_run(
    sleeps: list[float],
) -> None:
    route = respx.get(FORECAST_URL).mock(return_value=httpx.Response(429))
    with pytest.raises(httpx.TransportError, match="429"):
        OpenMeteoClient()._get(FORECAST_URL, {})
    assert route.call_count == 6
    assert len(sleeps) == 5


@respx.mock
def test_a_client_error_is_not_retried(sleeps: list[float]) -> None:
    route = respx.get(FORECAST_URL).mock(return_value=httpx.Response(400))
    with pytest.raises(httpx.HTTPStatusError):
        OpenMeteoClient()._get(FORECAST_URL, {})
    assert route.call_count == 1
    assert sleeps == []
