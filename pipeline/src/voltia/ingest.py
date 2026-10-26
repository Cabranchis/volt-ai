"""Ingestion: fetch, validate and load each dataset. Safe to run repeatedly (requirement FR-04)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd
import structlog
from sqlalchemy import Engine

from voltia import db
from voltia.config import Settings
from voltia.schemas import (
    BatchValidationError,
    validate_daily,
    validate_entities,
    validate_hourly,
)
from voltia.sources.oni import OniClient
from voltia.sources.openmeteo import OpenMeteoClient
from voltia.sources.xm import XMClient

log = structlog.get_logger()

XM_DAILY_METRICS = {
    "DemaSIN": "demand_kwh",
    "AporEner": "inflows_kwh",
    "PorcApor": "inflows_pct",
    "AporEnerMediHist": "inflows_hist_mean_kwh",
    "PorcVoluUtilDiar": "reservoir_pct",
    "VoluUtilDiarEner": "reservoir_kwh",
}
# Market state read by the price model (features.MARKET_FEATURES). Daily metrics, then hourly
# ones averaged over the 24 hours. VertEner lists only the days with spilling.
XM_MARKET_DAILY = {
    "PrecEsca": "scarcity_price",
    "VolTurbMasa": "turbined_m3",
    "CapaUtilDiarEner": "reservoir_capacity_kwh",
}
XM_MARKET_HOURLY = {"CostMargDesp": "dispatch_cost"}
XM_SPILL_METRIC = "VertEner"
# Contract prices have weeks without a published value (a 34-day gap in 2018-2026), so they are a
# dataset of their own and may have holes; the model reads missing values as NaN.
XM_CONTRACT_DAILY = {"PrecPromCont": "contract_price"}
XM_CONTRACT_HOURLY = {"PrecPromContNoRegu": "contract_price_unreg"}

# Per reservoir and per river, for the map. XM names the hydrological regions; "RIOS ESTIMADOS" is
# a bucket of estimated rivers with no place on a map, so it is left out.
XM_RESERVOIR_METRICS = {
    "VoluUtilDiarEner": "reservoir_kwh",
    "CapaUtilDiarEner": "reservoir_capacity_kwh",
}
XM_RIVER_METRICS = {"AporEner": "inflows_kwh", "AporEnerMediHist": "inflows_hist_mean_kwh"}
HYDRO_REGIONS = frozenset({"ANTIOQUIA", "CALDAS", "CARIBE", "CENTRO", "ORIENTE", "VALLE"})
# A river XM reports but does not list in ListadoRios (Amoya, in Tolima).
UNLISTED_RIVER_REGION = {"AMOYA": "CENTRO"}

MIX_CATEGORIES = ["hydro", "thermal", "solar", "wind", "cogen", "other"]
HOURS_PER_DAY = 24
DEMAND_TOLERANCE = 0.08  # demand / generation stays within about -3 % to +5 % in every year


@dataclass(frozen=True)
class Batch:
    """What a dataset produced: a long daily frame and optionally a long hourly frame."""

    daily: pd.DataFrame = field(default_factory=pd.DataFrame)
    hourly: pd.DataFrame | None = None
    continuous: bool = True
    # Values per reservoir or river (metric, entity, day, value) and their regions (kind, entity,
    # region); they go to their own tables, not to series_daily.
    entities: pd.DataFrame | None = None
    catalog: pd.DataFrame | None = None

    @property
    def is_empty(self) -> bool:
        no_entities = self.entities is None or self.entities.empty
        return self.daily.empty and no_entities


@dataclass(frozen=True)
class Clients:
    xm: XMClient
    meteo: OpenMeteoClient
    oni: OniClient


@dataclass(frozen=True)
class Result:
    dataset: str
    ok: bool
    rows: int
    last_day: date | None
    detail: str


def _daily_long(frame: pd.DataFrame, series: str, value_col: str = "value") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series": series,
            "day": pd.to_datetime(frame["day"]),
            "value": frame[value_col].astype(float),
        }
    )


def _complete_days(hourly: pd.DataFrame) -> pd.DataFrame:
    """Keep only days with all 24 hours; a partial day would bias daily means and sums."""
    counts = hourly.groupby("day")["hour"].transform("nunique")
    return hourly[counts == HOURS_PER_DAY]


def _recent_hourly(hourly: pd.DataFrame, series: str, today: date, keep_days: int) -> pd.DataFrame:
    cutoff = pd.Timestamp(today - timedelta(days=keep_days))
    recent = hourly[hourly["day"] >= cutoff]
    return pd.DataFrame(
        {
            "series": series,
            "day": recent["day"],
            "hour": recent["hour"].astype(int),
            "value": recent["value"].astype(float),
        }
    )


def settled_demand(demand: pd.DataFrame, generation: pd.DataFrame) -> pd.DataFrame:
    """Keep the demand days that reconcile with the day's total generation.

    XM publishes a placeholder for the newest day (2026-10-22 was 259 840 kWh instead of ~245 GWh)
    and the value passes range checks when it is only partly settled. Generation of a complete
    24-hour day tracks demand within 0.97 to 1.05 over 2018-2025, so a day is accepted only if
    both exist and agree within DEMAND_TOLERANCE.
    """
    merged = demand.merge(generation, on="day", suffixes=("", "_gen"))
    ratio = merged["value"] / merged["value_gen"]
    kept = merged[(ratio - 1).abs() <= DEMAND_TOLERANCE]
    dropped = len(demand) - len(kept)
    if dropped:
        log.warning("ingest.demand.unsettled_days_dropped", dropped=dropped)
    return kept[["day", "value"]]


def fetch_xm_daily(c: Clients, s: Settings, start: date, end: date, today: date) -> Batch:
    generation = _complete_days(c.xm.hourly_system("Gene", start, end))
    gen_totals = generation.groupby("day")["value"].sum().rename("value").reset_index()
    parts = []
    for metric, series in XM_DAILY_METRICS.items():
        frame = c.xm.daily_system(metric, start, end)
        if series == "demand_kwh":
            frame = settled_demand(frame, gen_totals)
        parts.append(_daily_long(frame, series))
    return Batch(daily=pd.concat(parts, ignore_index=True))


def fetch_xm_price(c: Clients, s: Settings, start: date, end: date, today: date) -> Batch:
    hourly = _complete_days(c.xm.hourly_system("PrecBolsNaci", start, end))
    grouped = hourly.groupby("day")["value"]
    daily = pd.concat(
        [
            _daily_long(grouped.mean().rename("value").reset_index(), "price_mean_cop_kwh"),
            _daily_long(grouped.max().rename("value").reset_index(), "price_max_cop_kwh"),
        ],
        ignore_index=True,
    )
    return Batch(
        daily=daily, hourly=_recent_hourly(hourly, "price_cop_kwh", today, s.hourly_retention_days)
    )


def _hourly_means(
    c: Clients, metrics: dict[str, str], start: date, end: date
) -> list[pd.DataFrame]:
    parts = []
    for metric, series in metrics.items():
        hourly = _complete_days(c.xm.hourly_system(metric, start, end))
        mean = hourly.groupby("day")["value"].mean().rename("value").reset_index()
        parts.append(_daily_long(mean, series))
    return parts


def fetch_xm_contracts(c: Clients, s: Settings, start: date, end: date, today: date) -> Batch:
    """Average contract prices, all and unregulated markets; published about five days late."""
    parts = [
        _daily_long(c.xm.daily_system(metric, start, end), series)
        for metric, series in XM_CONTRACT_DAILY.items()
    ]
    parts += _hourly_means(c, XM_CONTRACT_HOURLY, start, end)
    return Batch(daily=pd.concat(parts, ignore_index=True), continuous=False)


def fetch_xm_market(c: Clients, s: Settings, start: date, end: date, today: date) -> Batch:
    """Dispatch cost, scarcity price, spilling and the turbined volume and usable capacity."""
    daily = {
        series: c.xm.daily_system(metric, start, end) for metric, series in XM_MARKET_DAILY.items()
    }
    parts = [_daily_long(frame, series) for series, frame in daily.items()]
    parts += _hourly_means(c, XM_MARKET_HOURLY, start, end)
    # XM reports spilling only on the days it happened: a day the turbined volume is published
    # for but spilling is not listed had none. The newest turbined day is the exception, because
    # spilling may simply not be published yet, so it stays empty unless XM listed it.
    spill = c.xm.daily_system(XM_SPILL_METRIC, start, end).set_index("day")["value"]
    published = pd.DatetimeIndex(daily["turbined_m3"]["day"]).sort_values()
    settled = published[:-1] if len(published) else published
    days = pd.DatetimeIndex(settled.union(pd.DatetimeIndex(spill.index.intersection(published))))
    full = spill.reindex(days).fillna(0.0).rename("value").rename_axis("day").reset_index()
    parts.append(_daily_long(full, "spill_kwh"))
    return Batch(daily=pd.concat(parts, ignore_index=True))


def fetch_xm_regional(c: Clients, s: Settings, start: date, end: date, today: date) -> Batch:
    """Volume and capacity per reservoir, inflow and its historical mean per river, with regions."""
    reservoirs = c.xm.hydro_catalog("reservoir")
    rivers = c.xm.hydro_catalog("river")
    unlisted = [(n, r) for n, r in UNLISTED_RIVER_REGION.items() if n not in set(rivers["entity"])]
    rivers = pd.concat([rivers, pd.DataFrame(unlisted, columns=["entity", "region"])])
    catalog = pd.concat(
        [reservoirs.assign(kind="reservoir"), rivers.assign(kind="river")], ignore_index=True
    )
    catalog = catalog[catalog["region"].isin(HYDRO_REGIONS)][["kind", "entity", "region"]]
    parts = []
    for kind, entity_id, metrics in (
        ("reservoir", "Embalse", XM_RESERVOIR_METRICS),
        ("river", "Rio", XM_RIVER_METRICS),
    ):
        known = set(catalog.loc[catalog["kind"] == kind, "entity"])
        for metric, name in metrics.items():
            frame = c.xm.daily_entities(metric, entity_id, start, end)
            parts.append(frame[frame["entity"].isin(known)].assign(metric=name))
    entities = pd.concat(parts, ignore_index=True)[["metric", "entity", "day", "value"]]
    return Batch(entities=entities, catalog=catalog)


def fetch_xm_generation(c: Clients, s: Settings, start: date, end: date, today: date) -> Batch:
    hourly = _complete_days(c.xm.hourly_system("Gene", start, end))
    totals = hourly.groupby("day")["value"].sum().rename("value").reset_index()
    return Batch(
        daily=_daily_long(totals, "gen_total_kwh"),
        hourly=_recent_hourly(hourly, "generation_kwh", today, s.hourly_retention_days),
    )


def fetch_xm_mix(c: Clients, s: Settings, start: date, end: date, today: date) -> Batch:
    catalog = c.xm.resource_catalog()
    mix = c.xm.generation_mix(start, end, catalog)
    if mix.empty:
        return Batch(daily=pd.DataFrame(columns=["series", "day", "value"]))
    wide = mix.pivot(index="day", columns="category", values="kwh").reindex(columns=MIX_CATEGORIES)
    wide = wide.fillna(0.0)
    long = wide.reset_index().melt(id_vars="day", var_name="category", value_name="value")
    long["series"] = "gen_" + long["category"] + "_kwh"
    return Batch(daily=long[["series", "day", "value"]])


def fetch_weather(c: Clients, s: Settings, start: date, end: date, today: date) -> Batch:
    weather = c.meteo.weather(start, end, today)
    if weather.empty:
        return Batch(daily=pd.DataFrame(columns=["series", "day", "value"]))
    daily = pd.concat(
        [
            _daily_long(weather, "weather_temp_c", "temp_c"),
            _daily_long(weather, "weather_precip_mm", "precip_mm"),
        ],
        ignore_index=True,
    )
    return Batch(daily=daily)


def fetch_oni(c: Clients, s: Settings, start: date, end: date, today: date) -> Batch:
    # The file is tiny and publishes one row per month, so it is always read whole.
    oni = c.oni.fetch()
    oni = oni[oni["day"] >= pd.Timestamp(s.history_start)]
    return Batch(daily=_daily_long(oni, "oni"), continuous=False)


Fetcher = Callable[[Clients, Settings, date, date, date], Batch]

# Datasets only the price model's market features need. When one fails the run goes on: the
# features are then missing (NaN) for the newest days, which the trees treat as unknown.
OPTIONAL_DATASETS = frozenset({"xm_market", "xm_contracts", "xm_regional"})

DATASETS: dict[str, Fetcher] = {
    "xm_daily": fetch_xm_daily,
    "xm_price": fetch_xm_price,
    "xm_market": fetch_xm_market,
    "xm_contracts": fetch_xm_contracts,
    "xm_regional": fetch_xm_regional,
    "xm_generation": fetch_xm_generation,
    "xm_mix": fetch_xm_mix,
    "weather": fetch_weather,
    "oni": fetch_oni,
}


def run_dataset(
    engine: Engine,
    clients: Clients,
    settings: Settings,
    name: str,
    since: date,
    today: date,
    full: bool,
) -> Result:
    """Ingest one dataset. On any failure the previous data stays and the log records the error."""
    last = db.get_last_day(engine, name)
    start = (
        since
        if (full or last is None)
        else max(since, last - timedelta(days=settings.revision_window_days))
    )
    end = today - timedelta(days=1)
    try:
        batch = DATASETS[name](clients, settings, start, end, today)
        if batch.is_empty:
            raise BatchValidationError("the source returned no data for the requested range")
        days = []
        rows = 0
        if not batch.daily.empty:
            daily = validate_daily(batch.daily, continuous=batch.continuous)
            rows += db.upsert_series_daily(engine, daily)
            days.append(daily["day"].max())
        if batch.entities is not None and not batch.entities.empty:
            entities = validate_entities(batch.entities)
            rows += db.upsert_entity_daily(engine, entities)
            if batch.catalog is not None:
                db.replace_entity_catalog(engine, batch.catalog)
            days.append(entities["day"].max())
        if batch.hourly is not None and not batch.hourly.empty:
            rows += db.upsert_series_hourly(engine, validate_hourly(batch.hourly))
        db.prune_hourly(engine, today, settings.hourly_retention_days)
        last_day = pd.Timestamp(max(days)).date()
        db.log_ingest(engine, name, last_day, "ok", f"{rows} rows from {start} to {end}")
        log.info("ingest.ok", dataset=name, rows=rows, last_day=last_day.isoformat())
        return Result(name, True, rows, last_day, "ok")
    except Exception as exc:
        db.log_ingest(engine, name, None, "error", f"{type(exc).__name__}: {exc}"[:500])
        log.error("ingest.failed", dataset=name, error=str(exc))
        return Result(name, False, 0, last, f"{type(exc).__name__}: {exc}")


def run_all(
    engine: Engine,
    clients: Clients,
    settings: Settings,
    since: date,
    today: date,
    full: bool,
    only: list[str] | None = None,
) -> list[Result]:
    names = only or list(DATASETS)
    return [run_dataset(engine, clients, settings, n, since, today, full) for n in names]
