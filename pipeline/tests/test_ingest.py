"""End-to-end ingestion on SQLite with every external API replaced by recorded responses."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from typing import Any

import httpx
import pandas as pd
import pytest
import respx
from sqlalchemy import Engine

from voltia import db
from voltia.config import Settings
from voltia.ingest import (
    MIX_CATEGORIES,
    XM_CONTRACT_DAILY,
    XM_CONTRACT_HOURLY,
    XM_DAILY_METRICS,
    XM_MARKET_DAILY,
    XM_MARKET_HOURLY,
    XM_SPILL_METRIC,
    Clients,
    fetch_xm_market,
    run_all,
    settled_demand,
)
from voltia.schemas import DAILY_BOUNDS
from voltia.sources.oni import ONI_URL, OniClient
from voltia.sources.openmeteo import FORECAST_URL, OpenMeteoClient
from voltia.sources.xm import XMClient, XMTransientError

BASE = "https://servapibi.xm.com.co"
DEMAND_KWH = 248.0e6  # matches the recorded generation of 2026-10-20
TODAY = date(2026, 10, 22)
SINCE = date(2026, 10, 20)


DAILY_METRICS = {
    **XM_DAILY_METRICS,
    **XM_MARKET_DAILY,
    **XM_CONTRACT_DAILY,
    XM_SPILL_METRIC: "spill_kwh",
}
HOURLY_METRICS = {**XM_MARKET_HOURLY, **XM_CONTRACT_HOURLY}


def _daily_payload(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    series = DAILY_METRICS[body["MetricId"]]
    low, high = DAILY_BOUNDS[series]
    value = DEMAND_KWH if series == "demand_kwh" else (low + high) / 2
    start, end = date.fromisoformat(body["StartDate"]), date.fromisoformat(body["EndDate"])
    days = (end - start).days + 1
    if series == "spill_kwh":
        days = 1  # XM lists spilling only on the days it happened
    items = [
        {
            "Date": (start + timedelta(days=i)).isoformat(),
            "DailyEntities": [{"Id": "Sistema", "Value": str(value)}],
        }
        for i in range(days)
    ]
    return httpx.Response(200, json={"Items": items})


def _weather_payload(_request: httpx.Request) -> httpx.Response:
    days = [(SINCE + timedelta(days=i)).isoformat() for i in range(3)]
    city = {
        "daily": {
            "time": days,
            "temperature_2m_mean": [18.0, 19.0, 20.0],
            "precipitation_sum": [1.0, 0.0, 4.0],
        }
    }
    return httpx.Response(200, json=[city, city, city, city])


@pytest.fixture
def mocked_apis(
    load_json: Callable[[str], Any], read_text: Callable[[str], str]
) -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{BASE}/daily").mock(side_effect=_daily_payload)

        def hourly(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            if body["MetricId"] == "PrecBolsNaci" or body["MetricId"] in HOURLY_METRICS:
                return httpx.Response(200, json=load_json("xm/hourly_price.json"))
            if body["Entity"] == "Recurso":
                return httpx.Response(200, json=load_json("xm/hourly_gene_resources.json"))
            return httpx.Response(200, json=load_json("xm/hourly_gene_system.json"))

        router.post(f"{BASE}/hourly").mock(side_effect=hourly)
        router.post(f"{BASE}/lists").mock(
            return_value=httpx.Response(200, json=load_json("xm/resource_catalog.json"))
        )
        router.get(FORECAST_URL).mock(side_effect=_weather_payload)
        router.get(ONI_URL).mock(
            return_value=httpx.Response(200, text=read_text("other/oni_sample.txt"))
        )
        yield router


@pytest.fixture
def clients() -> Clients:
    return Clients(XMClient(), OpenMeteoClient(), OniClient())


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_full_ingest_loads_every_dataset(
    mocked_apis: respx.MockRouter, engine: Engine, clients: Clients, settings: Settings
) -> None:
    results = run_all(engine, clients, settings, SINCE, TODAY, full=True)
    assert [r.dataset for r in results if not r.ok] == []
    wide = db.read_series(engine)
    expected = {
        *DAILY_METRICS.values(),
        *HOURLY_METRICS.values(),
        "price_mean_cop_kwh",
        "price_max_cop_kwh",
        "gen_total_kwh",
        *(f"gen_{c}_kwh" for c in MIX_CATEGORIES),
        "weather_temp_c",
        "weather_precip_mm",
        "oni",
    }
    assert expected == set(wide.columns)
    assert wide["weather_temp_c"].dropna().tolist() == [18.0, 19.0]
    # Only 2026-10-20 has recorded generation to reconcile with, so 2026-10-21 demand is held back.
    assert wide["demand_kwh"].dropna().index.tolist() == [pd.Timestamp("2026-10-20")]
    assert wide["gen_wind_kwh"].dropna().eq(0).all() or wide["gen_wind_kwh"].dropna().gt(0).all()
    # Spilling was listed for the first day only; the newest turbined day stays empty because XM
    # may not have published its spilling yet.
    spill = wide["spill_kwh"].dropna()
    assert spill.index.tolist() == [pd.Timestamp("2026-10-20")]
    assert spill.iloc[0] > 0
    assert wide["dispatch_cost"].dropna().gt(0).all()
    assert db.table_counts(engine, ["series_hourly"])["series_hourly"] == 48 + 24


def test_ingest_is_idempotent(
    mocked_apis: respx.MockRouter, engine: Engine, clients: Clients, settings: Settings
) -> None:
    run_all(engine, clients, settings, SINCE, TODAY, full=True)
    before = db.table_counts(engine, ["series_daily", "series_hourly"])
    results = run_all(engine, clients, settings, SINCE, TODAY, full=False)
    assert all(r.ok for r in results)
    assert db.table_counts(engine, ["series_daily", "series_hourly"]) == before


def test_one_failing_dataset_does_not_block_the_others(
    monkeypatch: pytest.MonkeyPatch,
    mocked_apis: respx.MockRouter,
    load_json: Callable[[str], Any],
    engine: Engine,
    clients: Clients,
    settings: Settings,
) -> None:
    monkeypatch.setattr(XMClient._post.retry, "sleep", lambda _s: None)  # type: ignore[attr-defined]
    generation = load_json("xm/hourly_gene_system.json")

    def hourly(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["Entity"] == "Recurso":
            return httpx.Response(503)
        return httpx.Response(200, json=generation)

    mocked_apis.post(f"{BASE}/hourly").mock(side_effect=hourly)
    only = ["xm_daily", "xm_mix"]
    results = {r.dataset: r for r in run_all(engine, clients, settings, SINCE, TODAY, True, only)}
    assert results["xm_daily"].ok
    assert not results["xm_mix"].ok
    assert XMTransientError.__name__ in results["xm_mix"].detail
    with engine.connect() as conn:
        statuses = dict(conn.exec_driver_sql("SELECT dataset, status FROM ingest_log").all())
    assert statuses == {"xm_daily": "ok", "xm_mix": "error"}
    assert "demand_kwh" in db.read_series(engine).columns


def test_invalid_batch_is_rejected_and_nothing_is_stored(
    mocked_apis: respx.MockRouter, engine: Engine, clients: Clients, settings: Settings
) -> None:
    mocked_apis.post(f"{BASE}/daily").mock(
        return_value=httpx.Response(
            200,
            json={
                "Items": [
                    {"Date": "2026-10-20", "DailyEntities": [{"Id": "Sistema", "Value": "-5"}]}
                ]
            },
        )
    )
    [result] = run_all(engine, clients, settings, SINCE, TODAY, True, ["xm_daily"])
    assert not result.ok
    assert "BatchValidationError" in result.detail
    assert db.table_counts(engine, ["series_daily"]) == {"series_daily": 0}


def test_partial_days_are_dropped(
    mocked_apis: respx.MockRouter,
    load_json: Callable[[str], Any],
    engine: Engine,
    clients: Clients,
    settings: Settings,
) -> None:
    payload = load_json("xm/hourly_price.json")
    values = payload["Items"][1]["HourlyEntities"][0]["Values"]
    del values["Hour24"]  # second day incomplete
    mocked_apis.post(f"{BASE}/hourly").mock(return_value=httpx.Response(200, json=payload))
    [result] = run_all(engine, clients, settings, SINCE, TODAY, True, ["xm_price"])
    assert result.ok
    assert len(db.read_series(engine, ["price_mean_cop_kwh"])) == 1


def test_settled_demand_drops_placeholder_and_unmatched_days() -> None:
    days = pd.to_datetime(["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"])
    demand = pd.DataFrame({"day": days, "value": [248.5e6, 245.3e6, 259_840.0, 240e6]})
    generation = pd.DataFrame({"day": days[:3], "value": [248.3e6, 245.3e6, 240e6]})
    kept = settled_demand(demand, generation)
    # 10-22 is the placeholder, 10-23 has no generation to compare with.
    assert kept["day"].tolist() == list(days[:2])


class _MarketXM:
    """Three turbined days; spilling is listed for the first only."""

    def daily_system(self, metric: str, start: date, end: date) -> pd.DataFrame:
        days = pd.to_datetime(["2026-10-18", "2026-10-19", "2026-10-20"])
        if metric == XM_SPILL_METRIC:
            return pd.DataFrame({"day": days[:1], "value": [5e6]})
        return pd.DataFrame({"day": days, "value": [1.0e8] * 3})

    def hourly_system(self, metric: str, start: date, end: date) -> pd.DataFrame:
        days = pd.to_datetime(["2026-10-18", "2026-10-19", "2026-10-20"]).repeat(24)
        return pd.DataFrame({"day": days, "hour": list(range(1, 25)) * 3, "value": 300.0})


def test_spill_is_zero_on_settled_unlisted_days_and_empty_on_the_newest(settings: Settings) -> None:
    clients = Clients(_MarketXM(), None, None)  # type: ignore[arg-type]
    batch = fetch_xm_market(clients, settings, SINCE, TODAY, TODAY)
    spill = batch.daily[batch.daily["series"] == "spill_kwh"].set_index("day")["value"]
    assert spill.to_dict() == {pd.Timestamp("2026-10-18"): 5e6, pd.Timestamp("2026-10-19"): 0.0}
