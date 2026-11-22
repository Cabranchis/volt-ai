"""End-to-end ingestion on SQLite with every external API replaced by recorded responses."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import replace
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
    STEP_GUARDS,
    XM_CONTRACT_DAILY,
    XM_CONTRACT_HOURLY,
    XM_DAILY_METRICS,
    XM_MARKET_DAILY,
    XM_MARKET_HOURLY,
    XM_RESERVOIR_METRICS,
    XM_RIVER_METRICS,
    XM_SPILL_METRIC,
    Batch,
    Clients,
    fetch_xm_daily,
    fetch_xm_market,
    fetch_xm_mix,
    guard_steps,
    newest_day_of,
    plausible_hydrology,
    run_all,
    run_dataset,
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


RESERVOIRS = {"PENOL": "ANTIOQUIA", "GUAVIO": "ORIENTE", "FLORIDA II": "RIOS ESTIMADOS"}
RIVERS = {"GUATAPE": "ANTIOQUIA", "GUAVIO": "ORIENTE"}
# Reported by XM but not listed: a reservoir to drop and Amoya, which has a fixed region.
REPORTED = {"Embalse": [*RESERVOIRS, "NUEVO"], "Rio": [*RIVERS, "AMOYA"]}


def _entity_payload(body: dict[str, Any]) -> httpx.Response:
    start, end = date.fromisoformat(body["StartDate"]), date.fromisoformat(body["EndDate"])
    items = [
        {
            "Date": (start + timedelta(days=i)).isoformat(),
            "DailyEntities": [
                {"Id": body["Entity"], "Name": name, "Value": 1000.0 * (k + 1)}
                for k, name in enumerate(REPORTED[body["Entity"]])
            ],
        }
        for i in range((end - start).days + 1)
    ]
    return httpx.Response(200, json={"Items": items})


def _list_payload(regions: dict[str, str]) -> httpx.Response:
    items = [
        {
            "Date": "2026-10-25",
            "ListEntities": [{"Id": "Sistema", "Values": {"Name": name, "HydroRegion": region}}],
        }
        for name, region in regions.items()
    ]
    return httpx.Response(200, json={"Items": [*items, items[0]]})  # XM repeats some entries


def _daily_payload(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    if body["Entity"] in REPORTED:
        return _entity_payload(body)
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


MOCK = {"forecast_first": TODAY}


def _weather_payload(request: httpx.Request) -> httpx.Response:
    places = len(request.url.params["latitude"].split(","))
    if request.url.params.get("forecast_days") == "16":
        # the forecast request: the issue date and the 15 days after it
        count, first = 16, MOCK["forecast_first"]
    else:
        count, first = 3, SINCE
    days = [(first + timedelta(days=i)).isoformat() for i in range(count)]
    place = {
        "daily": {
            "time": days,
            "temperature_2m_mean": [18.0 + i for i in range(count)],
            "precipitation_sum": [float(i % 5) for i in range(count)],
        }
    }
    return httpx.Response(200, json=[place] * places)


def _hours(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [e["Values"] for item in payload["Items"] for e in item["HourlyEntities"]]


def _resources_adding_up(load_json: Callable[[str], Any]) -> dict[str, Any]:
    """The recorded resources, scaled so that they add up to the recorded system generation.

    The recording keeps a few resources only; in XM the resources of a day add up to the system
    total exactly, which is what the mix of a day is checked against.
    """
    system, resources = (
        load_json("xm/hourly_gene_system.json"),
        load_json("xm/hourly_gene_resources.json"),
    )
    keys = [f"Hour{h:02d}" for h in range(1, 25)]

    def total(payload: dict[str, Any]) -> float:
        return sum(float(v[k]) for v in _hours(payload) for k in keys if v.get(k) not in (None, ""))

    factor = total(system) / total(resources)
    for values in _hours(resources):
        for k in keys:
            if values.get(k) not in (None, ""):
                values[k] = str(float(values[k]) * factor)
    return resources


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
                return httpx.Response(200, json=_resources_adding_up(load_json))
            return httpx.Response(200, json=load_json("xm/hourly_gene_system.json"))

        router.post(f"{BASE}/hourly").mock(side_effect=hourly)

        def lists(request: httpx.Request) -> httpx.Response:
            metric = json.loads(request.content)["MetricId"]
            if metric == "ListadoEmbalses":
                return _list_payload(RESERVOIRS)
            if metric == "ListadoRios":
                return _list_payload(RIVERS)
            return httpx.Response(200, json=load_json("xm/resource_catalog.json"))

        router.post(f"{BASE}/lists").mock(side_effect=lists)
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


def _previous_load(engine: Engine) -> date:
    """A dataset that has loaded before, so the next update is a normal one."""
    last = TODAY - timedelta(days=3)
    db.log_ingest(engine, "xm_daily", last, "ok", "seed")
    return last


TIMEOUTS = httpx.ReadTimeout("timed out")


def test_a_dataset_that_exhausts_its_time_fails_without_calling_xm(
    engine: Engine, clients: Clients
) -> None:
    last = _previous_load(engine)
    budget_used_up = Settings(_env_file=None, xm_dataset_budget_s=-1.0)  # type: ignore[call-arg]
    with respx.mock(assert_all_called=False) as router:
        route = router.post(f"{BASE}/hourly").mock(side_effect=TIMEOUTS)
        result = run_dataset(engine, clients, budget_used_up, "xm_daily", SINCE, TODAY, full=False)
    assert not result.ok
    assert "timed out" in result.detail
    assert route.call_count == 0
    assert db.get_last_day(engine, "xm_daily") == last  # nothing new stored


def test_a_backfill_clears_a_budget_that_was_armed(
    monkeypatch: pytest.MonkeyPatch, engine: Engine, clients: Clients
) -> None:
    monkeypatch.setattr(XMClient._post.retry, "sleep", lambda _s: None)  # type: ignore[attr-defined]
    _previous_load(engine)
    budget_used_up = Settings(_env_file=None, xm_dataset_budget_s=-1.0)  # type: ignore[call-arg]
    with respx.mock(assert_all_called=False) as router:
        route = router.post(f"{BASE}/hourly").mock(side_effect=TIMEOUTS)
        run_dataset(engine, clients, budget_used_up, "xm_daily", SINCE, TODAY, full=False)
        assert route.call_count == 0  # the budget was armed
        result = run_dataset(engine, clients, budget_used_up, "xm_daily", SINCE, TODAY, full=True)
    assert not result.ok
    assert route.call_count > 0  # and the backfill removed it


def test_the_first_load_of_a_dataset_has_no_time_limit(
    monkeypatch: pytest.MonkeyPatch, engine: Engine, clients: Clients
) -> None:
    monkeypatch.setattr(XMClient._post.retry, "sleep", lambda _s: None)  # type: ignore[attr-defined]
    budget_used_up = Settings(_env_file=None, xm_dataset_budget_s=-1.0)  # type: ignore[call-arg]
    with respx.mock(assert_all_called=False) as router:
        route = router.post(f"{BASE}/hourly").mock(side_effect=TIMEOUTS)
        run_dataset(engine, clients, budget_used_up, "xm_daily", SINCE, TODAY, full=False)
    assert route.call_count > 0  # no previous load: it reads years, so no limit


def test_the_budget_grows_with_the_windows_a_gap_needs(
    monkeypatch: pytest.MonkeyPatch, engine: Engine, clients: Clients
) -> None:
    monkeypatch.setattr(XMClient._post.retry, "sleep", lambda _s: None)  # type: ignore[attr-defined]
    db.log_ingest(engine, "xm_daily", date(2026, 7, 1), "ok", "seed")
    seen: list[float | None] = []
    real = clients.xm.start_budget

    def spy(seconds: float | None) -> None:
        seen.append(seconds)
        real(seconds)

    monkeypatch.setattr(clients.xm, "start_budget", spy)
    settings = Settings(_env_file=None, xm_dataset_budget_s=100.0)  # type: ignore[call-arg]
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{BASE}/hourly").mock(side_effect=TIMEOUTS)
        run_dataset(engine, clients, settings, "xm_daily", date(2026, 1, 1), TODAY, full=False)
    # 2026-06-24 to 2026-10-21 is 120 days: four windows of at most 31 days.
    assert seen == [400.0]


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
    # 2 reservoirs x 2 metrics and 3 rivers x 2 metrics, for the 2 days; the unlisted reservoir
    # and the estimated-rivers region are dropped, Amoya gets its fixed region.
    assert db.table_counts(engine, ["entity_daily", "entity_catalog"]) == {
        "entity_daily": (2 * len(XM_RESERVOIR_METRICS) + 3 * len(XM_RIVER_METRICS)) * 2,
        "entity_catalog": 5,
    }
    with engine.connect() as conn:
        regions = dict(
            conn.exec_driver_sql("SELECT kind || ':' || entity, region FROM entity_catalog").all()
        )
        names = {r[0] for r in conn.exec_driver_sql("SELECT DISTINCT entity FROM entity_daily")}
    assert regions["river:AMOYA"] == "CENTRO"
    assert "reservoir:FLORIDA II" not in regions
    assert "NUEVO" not in names


def test_regional_dataset_failure_only_warns_and_keeps_what_was_stored(
    monkeypatch: pytest.MonkeyPatch,
    mocked_apis: respx.MockRouter,
    engine: Engine,
    clients: Clients,
    settings: Settings,
) -> None:
    monkeypatch.setattr(XMClient._post.retry, "sleep", lambda _s: None)  # type: ignore[attr-defined]
    [first] = run_all(engine, clients, settings, SINCE, TODAY, True, ["xm_regional"])
    assert first.ok
    stored = db.table_counts(engine, ["entity_daily", "entity_catalog"])
    mocked_apis.post(f"{BASE}/lists").mock(return_value=httpx.Response(503))
    [second] = run_all(engine, clients, settings, SINCE, TODAY, False, ["xm_regional"])
    assert not second.ok
    assert db.table_counts(engine, ["entity_daily", "entity_catalog"]) == stored


def test_weather_forecast_is_archived_once_per_issue_date(
    monkeypatch: pytest.MonkeyPatch,
    mocked_apis: respx.MockRouter,
    engine: Engine,
    clients: Clients,
    settings: Settings,
) -> None:
    [first] = run_all(engine, clients, settings, SINCE, TODAY, False, ["weather_forecast"])
    assert first.ok
    assert first.last_day == TODAY
    # 4 cities and 5 reservoir areas, today and the next 15 days
    assert db.table_counts(engine, ["weather_forecast_log"]) == {"weather_forecast_log": 9 * 16}
    # the same day again changes nothing; the next day adds its own forecast beside it
    run_all(engine, clients, settings, SINCE, TODAY, False, ["weather_forecast"])
    assert db.table_counts(engine, ["weather_forecast_log"]) == {"weather_forecast_log": 9 * 16}
    monkeypatch.setitem(MOCK, "forecast_first", TODAY + timedelta(days=1))
    run_all(
        engine, clients, settings, SINCE, TODAY + timedelta(days=1), False, ["weather_forecast"]
    )
    assert db.table_counts(engine, ["weather_forecast_log"]) == {"weather_forecast_log": 9 * 16 * 2}
    with engine.connect() as conn:
        models = {
            r[0] for r in conn.exec_driver_sql("SELECT DISTINCT model FROM weather_forecast_log")
        }
    assert models == {"gfs_seamless"}


def test_an_incomplete_weather_forecast_is_refused_and_stores_nothing(
    monkeypatch: pytest.MonkeyPatch,
    mocked_apis: respx.MockRouter,
    engine: Engine,
    clients: Clients,
    settings: Settings,
) -> None:
    # the API answers one day early: the forecast would be short of its last day
    monkeypatch.setitem(MOCK, "forecast_first", TODAY - timedelta(days=1))
    [result] = run_all(engine, clients, settings, SINCE, TODAY, False, ["weather_forecast"])
    assert not result.ok
    assert db.table_counts(engine, ["weather_forecast_log"]) == {"weather_forecast_log": 0}


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


class _XMStub:
    def start_budget(self, seconds: float | None) -> None:
        return None


class _MarketXM(_XMStub):
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


def _hydrology(rows: dict[str, list[float]], start: str = "2026-11-08") -> pd.DataFrame:
    """A long daily frame, one list of values per series, from `start`."""
    days = pd.date_range(start, periods=len(next(iter(rows.values()))))
    return pd.concat(
        [
            pd.DataFrame({"series": name, "day": days, "value": values})
            for name, values in rows.items()
        ],
        ignore_index=True,
    )


INCIDENT = {  # XM, 2026-11-12 11:09 UTC: the 11th arrived half published
    "reservoir_pct": [0.79188, 0.79212, 0.79068, 0.07639],
    "reservoir_kwh": [13.988e9, 13.992e9, 13.967e9, 1.351e9],
    "inflows_pct": [0.758, 0.521, 0.432, 0.054],
    "inflows_kwh": [205.6e6, 141.4e6, 117.1e6, 14.7e6],
    "inflows_hist_mean_kwh": [271.15e6] * 4,
}


def test_a_half_published_hydrology_day_is_dropped_for_every_series() -> None:
    kept = plausible_hydrology(_hydrology(INCIDENT))
    assert kept["day"].max() == pd.Timestamp("2026-11-10")
    assert kept.groupby("series")["day"].count().to_dict() == dict.fromkeys(INCIDENT, 3)


def test_real_extreme_hydrology_moves_are_kept() -> None:
    # The largest daily moves in 3 220 days from 2018: -2.2 and +3.5 points of reservoir level,
    # 0.9546 and 1.0518 times the stored volume, inflows at 0.452 of the previous day.
    rows = {
        "reservoir_pct": [0.60, 0.5777, 0.6124],
        "reservoir_kwh": [10.0e9, 9.546e9, 10.040e9],
        "inflows_kwh": [200e6, 90.4e6, 231e6],
    }
    frame = _hydrology(rows)
    assert len(plausible_hydrology(frame)) == len(frame)


def test_the_first_day_and_a_single_day_have_nothing_to_compare_with() -> None:
    frame = _hydrology({"reservoir_kwh": [1.0e9], "inflows_kwh": [1.0e6]})
    assert len(plausible_hydrology(frame)) == len(frame)


def test_two_bad_days_in_a_row_are_both_dropped() -> None:
    rows = {"reservoir_kwh": [13.9e9, 1.3e9, 1.2e9], "inflows_kwh": [117e6, 14e6, 13e6]}
    kept = plausible_hydrology(_hydrology(rows))
    assert kept["day"].tolist() == [pd.Timestamp("2026-11-08")] * 2  # one row per series


def test_partial_inflows_alone_drop_the_day() -> None:
    rows = {
        "reservoir_kwh": [13.9e9, 13.9e9],
        "inflows_kwh": [117e6, 14e6],
        "inflows_pct": [0.43, 0.05],
    }
    kept = plausible_hydrology(_hydrology(rows))
    assert kept["day"].max() == pd.Timestamp("2026-11-08")
    assert set(kept["series"]) == set(rows)


def test_other_series_pass_through_untouched() -> None:
    frame = pd.concat(
        [_hydrology(INCIDENT), _hydrology({"demand_kwh": [2.4e8, 2.5e8, 2.4e8, 2.5e8]})],
        ignore_index=True,
    )
    kept = plausible_hydrology(frame)
    assert (kept["series"] == "demand_kwh").sum() == 4


class _HydroXM(_XMStub):
    """XM answering `fetch_xm_daily` with the incident's hydrology and settled demand."""

    days = pd.date_range("2026-11-08", periods=4)

    def daily_system(self, metric: str, start: date, end: date) -> pd.DataFrame:
        series = XM_DAILY_METRICS[metric]
        values = INCIDENT.get(series, [248e6] * 4)
        return pd.DataFrame({"day": self.days, "value": values})

    def hourly_system(self, metric: str, start: date, end: date) -> pd.DataFrame:
        return pd.DataFrame(
            {"day": self.days.repeat(24), "hour": list(range(1, 25)) * 4, "value": 248e6 / 24}
        )


def test_fetch_xm_daily_stores_no_half_published_hydrology(settings: Settings) -> None:
    clients = Clients(_HydroXM(), None, None)  # type: ignore[arg-type]
    daily = fetch_xm_daily(clients, settings, SINCE, TODAY, TODAY).daily
    last = daily.groupby("series")["day"].max()
    assert last["reservoir_pct"] == pd.Timestamp("2026-11-10")
    assert last["inflows_pct"] == pd.Timestamp("2026-11-10")
    assert last["demand_kwh"] == pd.Timestamp("2026-11-11")  # demand has its own check


def test_a_half_published_capacity_day_is_dropped() -> None:
    frame = _hydrology({"reservoir_capacity_kwh": [17.7e9, 17.7e9, 1.5e9]})
    kept = plausible_hydrology(frame, ("reservoir_capacity_kwh",))
    assert kept["day"].max() == pd.Timestamp("2026-11-09")


def test_the_limits_are_sharp() -> None:
    def kept(ratio: float) -> bool:
        frame = _hydrology({"reservoir_kwh": [10e9, 10e9 * ratio]})
        return len(plausible_hydrology(frame)) == 2

    assert kept(0.86)
    assert kept(1.14)
    assert not kept(0.84)
    assert not kept(1.16)
    assert len(plausible_hydrology(_hydrology({"inflows_kwh": [100e6, 26e6]}))) == 2
    assert len(plausible_hydrology(_hydrology({"inflows_kwh": [100e6, 24e6]}))) == 1


def test_a_half_published_percentage_is_caught_even_if_the_volume_is_missing() -> None:
    # XM lists each metric on its own: the percentage can exist for a day the volume does not.
    frame = pd.concat(
        [
            _hydrology({"reservoir_pct": [0.79, 0.076]}),
            _hydrology({"reservoir_kwh": [13.97e9]}),
        ],
        ignore_index=True,
    )
    kept = plausible_hydrology(frame)
    assert kept[kept["series"] == "reservoir_pct"]["day"].tolist() == [pd.Timestamp("2026-11-08")]


class _CapacityXM(_MarketXM):
    """The market fixture with a half published capacity on the newest day."""

    def daily_system(self, metric: str, start: date, end: date) -> pd.DataFrame:
        frame = super().daily_system(metric, start, end)
        if XM_MARKET_DAILY.get(metric) == "reservoir_capacity_kwh":
            frame["value"] = [17.7e9, 17.7e9, 1.5e9]
        return frame


def test_fetch_xm_market_drops_only_the_bad_capacity_day(settings: Settings) -> None:
    clients = Clients(_CapacityXM(), None, None)  # type: ignore[arg-type]
    daily = fetch_xm_market(clients, settings, SINCE, TODAY, TODAY).daily
    last = daily.groupby("series")["day"].max()
    assert last["reservoir_capacity_kwh"] == pd.Timestamp("2026-10-19")
    assert last["turbined_m3"] == pd.Timestamp("2026-10-20")
    assert last["scarcity_price"] == pd.Timestamp("2026-10-20")


def test_duplicated_rows_are_left_for_the_validator() -> None:
    frame = _hydrology({"reservoir_kwh": [10e9, 10e9]})
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    assert len(plausible_hydrology(frame)) == 3


# --- Guards on the other series (price, market, contracts, generation) and on the batch itself ---

PRICE = ("price_mean_cop_kwh", "price_max_cop_kwh")


def _daily(rows: dict[str, list[float]], start: str = "2026-11-01") -> pd.DataFrame:
    days = pd.date_range(start, periods=len(next(iter(rows.values()))))
    return pd.concat(
        [pd.DataFrame({"series": n, "day": days, "value": v}) for n, v in rows.items()],
        ignore_index=True,
    )


def _price_batch(mean: list[float], high: list[float]) -> Batch:
    return Batch(daily=_daily({PRICE[0]: mean, PRICE[1]: high}))


def test_a_price_in_the_wrong_unit_is_dropped_with_its_group() -> None:
    batch = _price_batch(
        [500.0, 510.0, 0.52], [900.0, 950.0, 1.1]
    )  # the last day is in thousandths
    kept = guard_steps(batch, STEP_GUARDS["xm_price"], {}).daily
    assert kept["day"].max() == pd.Timestamp("2026-11-02")
    assert len(kept) == 4


def test_the_first_day_is_compared_with_the_stored_value() -> None:
    batch = _price_batch([500.0, 510.0], [900.0, 950.0])
    assert len(guard_steps(batch, STEP_GUARDS["xm_price"], {}).daily) == 4  # nothing to compare
    batch = _price_batch([0.52, 510.0], [1.1, 950.0])
    day = pd.Timestamp("2026-10-31")
    anchors = {PRICE[0]: (day, 500.0), PRICE[1]: (day, 900.0)}
    kept = guard_steps(batch, STEP_GUARDS["xm_price"], anchors).daily
    assert kept["day"].tolist() == [pd.Timestamp("2026-11-02")] * 2


def test_the_largest_real_moves_of_2018_2026_are_kept() -> None:
    # Mean price x2.739 and x0.369, maximum price x7.667 and x0.131 in a day (measured extremes).
    batch = _price_batch([100.0, 273.9, 101.0], [100.0, 766.7, 100.5])
    assert len(guard_steps(batch, STEP_GUARDS["xm_price"], {}).daily) == 6
    batch = _price_batch([1000.0, 369.0], [1000.0, 131.0])
    assert len(guard_steps(batch, STEP_GUARDS["xm_price"], {}).daily) == 4


def test_hourly_rows_of_a_dropped_day_go_with_it() -> None:
    hourly = pd.DataFrame(
        {
            "series": "price_cop_kwh",
            "day": pd.to_datetime(["2026-11-02"] * 2 + ["2026-11-03"] * 2),
            "hour": [1, 2, 1, 2],
            "value": [500.0, 510.0, 0.5, 0.5],
        }
    )
    batch = replace(_price_batch([500.0, 510.0, 0.52], [900.0, 950.0, 1.1]), hourly=hourly)
    kept = guard_steps(batch, STEP_GUARDS["xm_price"], {})
    assert kept.hourly is not None
    assert kept.hourly["day"].max() == pd.Timestamp("2026-11-02")


def test_last_values_gives_the_newest_recent_value_before_the_batch(engine: Engine) -> None:
    rows = pd.concat([_daily({PRICE[0]: [400.0, 410.0, 420.0]}, "2026-10-01")], ignore_index=True)
    db.upsert_series_daily(engine, rows)
    got = db.last_values(engine, [PRICE[0], PRICE[1]], date(2026, 10, 3), 31)
    # the 3rd is not before the 3rd; the second price has no rows
    assert got == {PRICE[0]: (pd.Timestamp("2026-10-02"), 410.0)}
    assert (
        db.last_values(engine, [PRICE[0]], date(2026, 12, 1), 31) == {}
    )  # too old to be a reference
    assert db.last_values(engine, [], date(2026, 10, 3), 31) == {}


class _PriceXM(_XMStub):
    """XM answering the hourly price with a good day and a newest day in the wrong unit."""

    def hourly_system(self, metric: str, start: date, end: date) -> pd.DataFrame:
        days = pd.to_datetime(["2026-10-19", "2026-10-20", "2026-10-21"]).repeat(24)
        values = [500.0] * 48 + [0.5] * 24
        return pd.DataFrame({"day": days, "hour": list(range(1, 25)) * 3, "value": values})


def test_a_bad_newest_price_day_is_not_stored_and_the_good_ones_stay(
    engine: Engine, settings: Settings
) -> None:
    clients = Clients(_PriceXM(), None, None)  # type: ignore[arg-type]
    result = run_all(engine, clients, settings, SINCE, TODAY, full=True, only=["xm_price"])[0]
    assert result.ok
    assert result.last_day == date(2026, 10, 20)
    stored = db.read_series(engine)[PRICE[0]].dropna()
    assert stored.index.max() == pd.Timestamp("2026-10-20")
    assert (stored == 500.0).all()


class _OverwriteXM(_XMStub):
    """A re-read whose days arrive in the wrong unit (20.5 still passes the price floor of 20)."""

    def hourly_system(self, metric: str, start: date, end: date) -> pd.DataFrame:
        days = pd.to_datetime(["2026-10-12", "2026-10-13"]).repeat(24)
        return pd.DataFrame({"day": days, "hour": list(range(1, 25)) * 2, "value": [20.5] * 48})


def test_a_re_read_cannot_overwrite_good_stored_days_with_a_bad_batch(
    engine: Engine, settings: Settings
) -> None:
    # Stored up to 10-11; the log says 10-19, so the re-read starts 7 days earlier, on 10-12,
    # and its reference is the value stored on 10-11 (it is before the batch, not in it).
    good = _daily({PRICE[0]: [500.0] * 4, PRICE[1]: [900.0] * 4}, "2026-10-08")
    db.upsert_series_daily(engine, good)
    db.log_ingest(engine, "xm_price", date(2026, 10, 19), "ok", "seed")
    clients = Clients(_OverwriteXM(), None, None)  # type: ignore[arg-type]
    since = date(2026, 10, 1)
    result = run_all(engine, clients, settings, since, TODAY, full=False, only=["xm_price"])[0]
    assert not result.ok  # every day was a placeholder, so nothing is left to store
    assert "series missing from the batch" in result.detail
    stored = db.read_series(engine)[PRICE[0]].dropna()
    assert stored.index.max() == pd.Timestamp("2026-10-11")
    assert (stored == 500.0).all()
    assert len(stored) == 4
    assert db.get_last_day(engine, "xm_price") == date(2026, 10, 19)  # unchanged


def test_a_new_level_that_lasts_is_accepted_after_three_days_and_never_freezes_the_series() -> None:
    # The price settles at ten times its level for good (or XM changes a unit): the first days are
    # held back, then the reference is too old to count and the new level is stored.
    level = [500.0, 510.0] + [5000.0] * 6
    batch = _price_batch(level, [2 * v for v in level])
    kept = guard_steps(batch, STEP_GUARDS["xm_price"], {}).daily
    days = sorted(kept[kept["series"] == PRICE[0]]["day"].dt.strftime("%m-%d").unique())
    assert days == ["11-01", "11-02", "11-06", "11-07", "11-08"]  # 11-03 to 11-05 held back


class _NoDemandXM(_HydroXM):
    """The demand metric comes back empty while the hydrology is fine (a renamed field upstream)."""

    def daily_system(self, metric: str, start: date, end: date) -> pd.DataFrame:
        if XM_DAILY_METRICS[metric] == "demand_kwh":
            return pd.DataFrame({"day": pd.to_datetime([]), "value": []})
        return super().daily_system(metric, start, end)


def test_a_missing_series_fails_the_batch_and_keeps_last_day(
    engine: Engine, settings: Settings
) -> None:
    db.log_ingest(engine, "xm_daily", date(2026, 10, 1), "ok", "seed")
    clients = Clients(_NoDemandXM(), None, None)  # type: ignore[arg-type]
    result = run_all(engine, clients, settings, SINCE, TODAY, full=True, only=["xm_daily"])[0]
    assert not result.ok
    assert "demand_kwh" in result.detail
    assert db.get_last_day(engine, "xm_daily") == date(2026, 10, 1)
    assert db.read_series(engine).empty


def test_last_day_is_the_newest_day_every_required_series_has() -> None:
    daily = pd.concat(
        [_daily({"demand_kwh": [2.4e8] * 3}), _daily({"reservoir_pct": [0.7] * 4})],
        ignore_index=True,
    )
    assert newest_day_of(daily, ("demand_kwh", "reservoir_pct")) == pd.Timestamp("2026-11-03")
    assert newest_day_of(daily, ()) == pd.Timestamp("2026-11-04")


class _PartialMixXM:
    """A mix of two days, the second only half published."""

    days = pd.to_datetime(["2026-10-19", "2026-10-20"])

    def resource_catalog(self) -> dict[str, str]:
        return {}

    def generation_mix(self, start: date, end: date, catalog: dict[str, str]) -> pd.DataFrame:
        return pd.DataFrame({"day": self.days, "category": "hydro", "kwh": [240e6, 120e6]})

    def hourly_system(self, metric: str, start: date, end: date) -> pd.DataFrame:
        days = self.days.repeat(24)
        return pd.DataFrame({"day": days, "hour": list(range(1, 25)) * 2, "value": 240e6 / 24})


def test_a_partly_published_mix_day_is_dropped(settings: Settings) -> None:
    clients = Clients(_PartialMixXM(), None, None)  # type: ignore[arg-type]
    daily = fetch_xm_mix(clients, settings, SINCE, TODAY, TODAY).daily
    assert daily["day"].unique().tolist() == [pd.Timestamp("2026-10-19")]
    assert len(daily) == len(MIX_CATEGORIES)
