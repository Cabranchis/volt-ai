from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd
import pytest

from voltia.sources.oni import parse_oni
from voltia.sources.openmeteo import parse_forecast, parse_weather


def test_parse_oni_uses_central_month(read_text: Callable[[str], str]) -> None:
    frame = parse_oni(read_text("other/oni_sample.txt"))
    last = frame.iloc[-1]
    assert last["day"] == pd.Timestamp("2026-08-01")  # JAS is centred on August
    assert last["value"] == 2.16


def test_parse_oni_maps_ndj_to_december() -> None:
    frame = parse_oni(" SEAS  YR   TOTAL   ANOM\n  NDJ 2025  25.96  -0.60\n")
    assert frame["day"].iloc[0] == pd.Timestamp("2025-12-01")


def test_parse_oni_ignores_header_and_noise() -> None:
    assert parse_oni("SEAS YR TOTAL ANOM\nnot a row\n").empty


def test_parse_weather_averages_cities(load_json: Callable[[str], Any]) -> None:
    payload = load_json("other/openmeteo_two_cities.json")
    frame = parse_weather(payload)
    assert list(frame.columns) == ["day", "temp_c", "precip_mm"]
    assert len(frame) == 3
    first = payload[0]["daily"]["temperature_2m_mean"][0]
    second = payload[1]["daily"]["temperature_2m_mean"][0]
    assert frame["temp_c"].iloc[0] == (first + second) / 2


def test_parse_weather_drops_days_without_data() -> None:
    payload = {
        "daily": {"time": ["2026-10-01"], "temperature_2m_mean": [None], "precipitation_sum": [1.0]}
    }
    assert parse_weather(payload).empty


def _place(first: date, days: int = 16, temperature: float | None = 20.0) -> dict[str, Any]:
    times = [(pd.Timestamp(first) + pd.Timedelta(days=i)).date().isoformat() for i in range(days)]
    return {
        "daily": {
            "time": times,
            "temperature_2m_mean": [temperature] * days,
            "precipitation_sum": [1.0] * days,
        }
    }


def test_parse_forecast_numbers_the_days_from_the_issue_date() -> None:
    issued = date(2026, 10, 22)
    frame = parse_forecast([_place(issued), _place(issued)], ["a", "b"], issued)
    assert frame["location"].value_counts().to_dict() == {"a": 16, "b": 16}
    assert sorted(frame["lead_days"].unique()) == list(range(16))
    assert set(frame["model"]) == {"gfs_seamless"}


@pytest.mark.parametrize(
    "place",
    [
        _place(date(2026, 10, 21)),  # starts a day early, so it ends a day short
        _place(date(2026, 10, 22), days=15),
        _place(date(2026, 10, 22), temperature=None),
    ],
)
def test_parse_forecast_refuses_an_incomplete_forecast(place: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"does not cover|missing"):
        parse_forecast([place], ["a"], date(2026, 10, 22))


def test_parse_forecast_rejects_a_payload_for_other_locations() -> None:
    with pytest.raises(ValueError, match="expected 2 locations"):
        parse_forecast([_place(date(2026, 10, 22))], ["a", "b"], date(2026, 10, 22))
