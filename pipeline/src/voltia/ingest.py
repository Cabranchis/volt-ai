"""Ingestion: fetch, validate and load each dataset. Safe to run repeatedly (requirement FR-04)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import structlog
from sqlalchemy import Engine

from voltia import db
from voltia.config import Settings
from voltia.schemas import BatchValidationError, validate_daily, validate_hourly
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
MIX_CATEGORIES = ["hydro", "thermal", "solar", "wind", "cogen", "other"]
HOURS_PER_DAY = 24
DEMAND_TOLERANCE = 0.08  # demand / generation stays within about -3 % to +5 % in every year


@dataclass(frozen=True)
class Batch:
    """What a dataset produced: a long daily frame and optionally a long hourly frame."""

    daily: pd.DataFrame
    hourly: pd.DataFrame | None = None
    continuous: bool = True


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

DATASETS: dict[str, Fetcher] = {
    "xm_daily": fetch_xm_daily,
    "xm_price": fetch_xm_price,
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
        if batch.daily.empty:
            raise BatchValidationError("the source returned no data for the requested range")
        daily = validate_daily(batch.daily, continuous=batch.continuous)
        rows = db.upsert_series_daily(engine, daily)
        if batch.hourly is not None and not batch.hourly.empty:
            rows += db.upsert_series_hourly(engine, validate_hourly(batch.hourly))
        db.prune_hourly(engine, today, settings.hourly_retention_days)
        last_day = pd.Timestamp(daily["day"].max()).date()
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
