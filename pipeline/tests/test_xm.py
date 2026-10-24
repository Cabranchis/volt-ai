from __future__ import annotations

import itertools
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx
import pandas as pd
import pytest
import respx

from voltia.sources import xm
from voltia.sources.xm import XMClient, XMError

BASE = "https://servapibi.xm.com.co"


def test_windows_split_into_31_day_chunks() -> None:
    chunks = list(xm.windows(date(2024, 1, 1), date(2024, 3, 10)))
    assert chunks[0] == (date(2024, 1, 1), date(2024, 1, 31))
    assert chunks[1] == (date(2024, 2, 1), date(2024, 3, 2))
    assert chunks[-1][1] == date(2024, 3, 10)
    assert all((e - s).days + 1 <= 31 for s, e in chunks)


def test_windows_cover_range_without_overlap() -> None:
    chunks = list(xm.windows(date(2018, 1, 1), date(2026, 10, 23)))
    for (_, prev_end), (next_start, _) in itertools.pairwise(chunks):
        assert (next_start - prev_end).days == 1


def test_windows_empty_when_end_before_start() -> None:
    assert list(xm.windows(date(2024, 2, 1), date(2024, 1, 1))) == []


def test_parse_daily(load_json: Callable[[str], Any]) -> None:
    frame = xm.parse_daily(load_json("xm/daily_demasin.json"))
    assert list(frame.columns) == ["day", "value"]
    assert len(frame) == 3
    # The recorded response ends with XM's placeholder for the newest, unsettled day.
    assert frame["value"].iloc[:2].between(1e8, 4e8).all()
    assert frame["value"].iloc[2] < 1e6
    assert frame["day"].is_monotonic_increasing


def test_parse_hourly_has_24_hours_per_day(load_json: Callable[[str], Any]) -> None:
    frame = xm.parse_hourly(load_json("xm/hourly_price.json"))
    assert len(frame) == 48
    assert set(frame["hour"]) == set(range(1, 25))
    assert (frame["value"] > 0).all()


def test_parse_hourly_skips_blank_hours() -> None:
    payload = {
        "Items": [
            {
                "Date": "2026-10-01",
                "HourlyEntities": [{"Id": "Sistema", "Values": {"Hour01": "5", "Hour02": ""}}],
            }
        ]
    }
    frame = xm.parse_hourly(payload)
    assert frame["hour"].tolist() == [1]


def test_generation_by_resource_sums_hours(load_json: Callable[[str], Any]) -> None:
    frame = xm.parse_generation_by_resource(load_json("xm/hourly_gene_resources.json"))
    assert {"day", "code", "kwh"} <= set(frame.columns)
    assert frame["code"].is_unique
    assert (frame["kwh"] >= 0).all()


def test_mix_maps_unknown_codes_to_other(load_json: Callable[[str], Any]) -> None:
    by_resource = xm.parse_generation_by_resource(load_json("xm/hourly_gene_resources.json"))
    catalog = xm.parse_resource_catalog(load_json("xm/resource_catalog.json"))
    mix = xm.mix_by_category(by_resource, catalog)
    assert "other" in set(mix["category"])
    assert "hydro" in set(mix["category"])
    assert mix["kwh"].sum() == pytest.approx(by_resource["kwh"].sum())


def test_catalog_normalises_type_case() -> None:
    payload = {
        "Items": [
            {"ListEntities": [{"Values": {"Code": "A", "Type": "Solar"}}]},
            {"ListEntities": [{"Values": {"Code": "B", "Type": "SOLAR"}}]},
        ]
    }
    assert xm.parse_resource_catalog(payload) == {"A": "solar", "B": "solar"}


@respx.mock
def test_error_text_raises_xm_error(read_text: Callable[[str], str]) -> None:
    respx.post(f"{BASE}/daily").mock(
        return_value=httpx.Response(200, text=read_text("xm/error_metric.txt"))
    )
    client = XMClient()
    with pytest.raises(XMError, match="no encontrada"):
        client.fetch("daily", "Nope", "Sistema", date(2026, 10, 1), date(2026, 10, 2))


@respx.mock
def test_retries_transient_failures(
    monkeypatch: pytest.MonkeyPatch, load_json: Callable[[str], Any]
) -> None:
    monkeypatch.setattr(XMClient._post.retry, "sleep", lambda _s: None)  # type: ignore[attr-defined]
    route = respx.post(f"{BASE}/daily").mock(
        side_effect=[
            httpx.Response(503),
            httpx.ConnectError("boom"),
            httpx.Response(200, json=load_json("xm/daily_demasin.json")),
        ]
    )
    frame = XMClient().daily_system("DemaSIN", date(2026, 10, 20), date(2026, 10, 22))
    assert route.call_count == 3
    assert len(frame) == 3


@respx.mock
def test_does_not_retry_client_errors() -> None:
    route = respx.post(f"{BASE}/daily").mock(return_value=httpx.Response(400, text="bad"))
    with pytest.raises(XMError):
        XMClient().fetch("daily", "DemaSIN", "Sistema", date(2026, 10, 1), date(2026, 10, 2))
    assert route.call_count == 1


def test_rejects_window_longer_than_31_days() -> None:
    with pytest.raises(ValueError, match="31"):
        XMClient().fetch("daily", "DemaSIN", "Sistema", date(2026, 1, 1), date(2026, 3, 1))


@respx.mock
def test_daily_system_splits_long_ranges(load_json: Callable[[str], Any]) -> None:
    route = respx.post(f"{BASE}/daily").mock(
        return_value=httpx.Response(200, json=load_json("xm/daily_demasin.json"))
    )
    XMClient().daily_system("DemaSIN", date(2026, 1, 1), date(2026, 3, 15))
    assert route.call_count == 3


def test_empty_range_returns_empty_frame() -> None:
    frame = XMClient().daily_system("DemaSIN", date(2026, 2, 1), date(2026, 1, 1))
    assert isinstance(frame, pd.DataFrame)
    assert frame.empty
