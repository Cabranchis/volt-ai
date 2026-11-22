"""Ingestion: fetch, validate and load each dataset. Safe to run repeatedly (requirement FR-04)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
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
    validate_weather_forecast,
)
from voltia.sources.oni import OniClient
from voltia.sources.openmeteo import OpenMeteoClient
from voltia.sources.xm import MAX_WINDOW_DAYS, XMClient

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
# Hydrology days published before XM has finished them (2026-11-12 11:09 UTC: the reservoir level
# of the 11th arrived as 0.076 when the day before was 0.791). Over 3 220 days from 2018 the daily
# ratio to the previous day stayed within 0.955 to 1.052 for the stored volume (0.972 to 1.052 for
# its percentage), 0.966 to 1.031 for the capacity and above 0.452 for the inflows. The limits leave
# about three times the range for the volume and the capacity; the inflows limit only catches
# drops of more than 75 %, because inflows vary a lot from day to day.
HYDRO_SERIES = (
    "reservoir_pct",
    "reservoir_kwh",
    "inflows_pct",
    "inflows_kwh",
    "inflows_hist_mean_kwh",
)
# Ratio of a day to the last accepted one: (lowest, highest), None for no limit.
HYDRO_STEP_LIMITS: dict[str, tuple[float | None, float | None]] = {
    "reservoir_pct": (0.85, 1.15),
    "reservoir_kwh": (0.85, 1.15),
    "reservoir_capacity_kwh": (0.85, 1.15),
    "inflows_pct": (0.25, None),
    "inflows_kwh": (0.25, None),
}

StepLimits = dict[str, tuple[float | None, float | None]]


@dataclass(frozen=True)
class StepGuard:
    """Series published together and the limits on their change from the last accepted day."""

    series: tuple[str, ...]
    limits: StepLimits
    hourly: tuple[str, ...] = ()  # hourly series dropped for the same days


# Measured on 3 218 days (2018-2026) as the ratio of a day to the previous observation: the mean
# price 0.37 to 2.74, the maximum price 0.13 to 7.67, the dispatch cost 0.32 to 3.27, the
# generation 0.86 to 1.21, the contract prices 0.87 to 1.17, the scarcity price 0.69 to 1.22 and
# the turbined volume 0.52 to 1.94. The limits leave at least a quarter more than the extremes,
# and still reject a zero or a value in the wrong unit (a thousandth of the real one).
STEP_GUARDS: dict[str, tuple[StepGuard, ...]] = {
    "xm_price": (
        StepGuard(
            ("price_mean_cop_kwh", "price_max_cop_kwh"),
            {"price_mean_cop_kwh": (0.1, 8.0), "price_max_cop_kwh": (0.05, 20.0)},
            hourly=("price_cop_kwh",),
        ),
    ),
    "xm_market": (
        StepGuard(
            ("dispatch_cost", "scarcity_price", "turbined_m3"),
            {
                "dispatch_cost": (0.1, 10.0),
                "scarcity_price": (0.5, 2.0),
                "turbined_m3": (0.25, 4.0),
            },
        ),
    ),
    "xm_contracts": (
        StepGuard(("contract_price",), {"contract_price": (0.7, 1.4)}),
        StepGuard(("contract_price_unreg",), {"contract_price_unreg": (0.7, 1.4)}),
    ),
    "xm_generation": (
        StepGuard(("gen_total_kwh",), {"gen_total_kwh": (0.6, 1.6)}, hourly=("generation_kwh",)),
    ),
}
# The value before a batch is only a reference when it is recent: after a long outage a real change
# can exceed the limits, and a reference that never matches would reject every later day.
ANCHOR_MAX_AGE_DAYS = 31
# A day is compared with the last accepted day only while that day is this close. A new level that
# lasts (a real regime change, a unit XM changed for good) is rejected for this many days and then
# accepted, so the guard can never freeze a series for good: without this the newest stored day
# would stay at the last day before the change, the next batch would start there again, and every
# run would reject the same days.
REFERENCE_MAX_GAP_DAYS = 3

# What each dataset must bring in every batch. A renamed or empty field upstream yields no rows for
# one series while the others load, and the dataset would still look current.
REQUIRED_SERIES: dict[str, tuple[str, ...]] = {
    "xm_daily": tuple(XM_DAILY_METRICS.values()),
    "xm_price": ("price_mean_cop_kwh", "price_max_cop_kwh"),
    "xm_generation": ("gen_total_kwh",),
    "xm_market": ("dispatch_cost", "scarcity_price", "turbined_m3", "reservoir_capacity_kwh"),
    "xm_mix": tuple(f"gen_{c}_kwh" for c in MIX_CATEGORIES),
    "weather": ("weather_temp_c", "weather_precip_mm"),
    "oni": ("oni",),
}
MIX_TOLERANCE = 0.005  # the mix sums to the system generation exactly over 2018-2026


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
    # Weather forecasts issued today, archived as first issued (not a daily series).
    weather_forecast: pd.DataFrame | None = None

    @property
    def is_empty(self) -> bool:
        no_entities = self.entities is None or self.entities.empty
        no_forecast = self.weather_forecast is None or self.weather_forecast.empty
        return self.daily.empty and no_entities and no_forecast


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


def drop_implausible_days(
    daily: pd.DataFrame,
    group: tuple[str, ...],
    limits: StepLimits,
    anchors: dict[str, tuple[pd.Timestamp, float]] | None = None,
) -> tuple[pd.DataFrame, dict[pd.Timestamp, str]]:
    """Drop the days of `group` whose change from the last accepted day is outside `limits`.

    A partly published day can pass range checks (a reservoir level of 0.076 is a number between
    0 and 1), so each guarded series is compared with its last accepted day. The series of a group
    come from one publication, so one failing series drops that day for all of them. `anchors`
    holds the last stored (day, value) of each series from before the batch: without it the first
    day has nothing to compare with and is kept. A reference more than `REFERENCE_MAX_GAP_DAYS`
    old is not used. A dropped day is refreshed by the next update, which
    re-reads the last days. Returns the kept rows and the dropped days with the reason.
    """
    if daily.duplicated(["series", "day"]).any():
        return daily, {}  # validate_daily names the duplicated rows
    wide = (
        daily[daily["series"].isin(group)]
        .pivot(index="day", columns="series", values="value")
        .sort_index()
    )
    last: dict[str, tuple[pd.Timestamp, float]] = dict(anchors or {})
    dropped: dict[pd.Timestamp, str] = {}
    for day, row in wide.iterrows():
        reason = None
        for name, (low, high) in limits.items():
            value = row.get(name)
            if name not in group or value is None or pd.isna(value):
                continue
            reference = last.get(name)
            if (
                reference
                and reference[1] > 0
                and (pd.Timestamp(str(day)) - reference[0]).days <= REFERENCE_MAX_GAP_DAYS
            ):
                ratio = value / reference[1]
                if (low is not None and ratio < low) or (high is not None and ratio > high):
                    reason = f"{name} {ratio:.3f} times the previous day"
                    break
        if reason:
            dropped[pd.Timestamp(str(day))] = reason
            continue
        for name in limits:
            value = row.get(name)
            if name in group and value is not None and not pd.isna(value):
                last[name] = (pd.Timestamp(str(day)), float(value))
    if not dropped:
        return daily, {}
    is_dropped = daily["series"].isin(group) & daily["day"].isin(list(dropped))
    return daily[~is_dropped].reset_index(drop=True), dropped


def plausible_hydrology(daily: pd.DataFrame, group: tuple[str, ...] = HYDRO_SERIES) -> pd.DataFrame:
    """Drop the days of `group` that XM published before finishing them (see drop_implausible_days).

    The limits are `HYDRO_STEP_LIMITS`, measured over 3 220 days: ratios 0.955 to 1.052 for the
    stored volume, 0.966 to 1.031 for the capacity and above 0.452 for the inflows.
    """
    kept, dropped = drop_implausible_days(daily, group, HYDRO_STEP_LIMITS)
    if dropped:
        log.warning(
            "ingest.hydrology.implausible_days_dropped",
            days={d.date().isoformat(): why for d, why in dropped.items()},
        )
    return kept


def guard_steps(
    batch: Batch,
    guards: tuple[StepGuard, ...],
    anchors: dict[str, tuple[pd.Timestamp, float]],
) -> Batch:
    """Apply the step guards of a dataset to its batch, daily and hourly rows alike."""
    daily, hourly = batch.daily, batch.hourly
    for guard in guards:
        daily, dropped = drop_implausible_days(daily, guard.series, guard.limits, anchors)
        if not dropped:
            continue
        log.warning(
            "ingest.steps.implausible_days_dropped",
            series=list(guard.series),
            days={d.date().isoformat(): why for d, why in dropped.items()},
        )
        if hourly is not None and guard.hourly:
            bad = hourly["series"].isin(guard.hourly) & hourly["day"].isin(list(dropped))
            hourly = hourly[~bad].reset_index(drop=True)
    return replace(batch, daily=daily, hourly=hourly)


def newest_day_of(daily: pd.DataFrame, required: tuple[str, ...]) -> pd.Timestamp:
    """The newest day every required series has; the newest day overall when none is required."""
    if not required:
        return pd.Timestamp(daily["day"].max())
    return pd.Timestamp(daily[daily["series"].isin(required)].groupby("series")["day"].max().min())


def fetch_xm_daily(c: Clients, s: Settings, start: date, end: date, today: date) -> Batch:
    generation = _complete_days(c.xm.hourly_system("Gene", start, end))
    gen_totals = generation.groupby("day")["value"].sum().rename("value").reset_index()
    parts = []
    for metric, series in XM_DAILY_METRICS.items():
        frame = c.xm.daily_system(metric, start, end)
        if series == "demand_kwh":
            frame = settled_demand(frame, gen_totals)
        parts.append(_daily_long(frame, series))
    return Batch(daily=plausible_hydrology(pd.concat(parts, ignore_index=True)))


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
    daily_all = plausible_hydrology(
        pd.concat(parts, ignore_index=True), ("reservoir_capacity_kwh",)
    )
    return Batch(daily=daily_all)


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
    # The mix adds up the hours each resource reported, so a day XM has only partly published has a
    # smaller mix with nothing to show it. It must match the day's system generation (24 hours).
    generation = _complete_days(c.xm.hourly_system("Gene", start, end))
    totals = generation.groupby("day")["value"].sum().reindex(wide.index)
    settled = ((wide.sum(axis=1) / totals) - 1).abs() <= MIX_TOLERANCE
    if not settled.all():
        log.warning("ingest.mix.partial_days_dropped", dropped=int((~settled).sum()))
    wide = wide[settled]
    long = wide.reset_index().melt(id_vars="day", var_name="category", value_name="value")
    long["series"] = "gen_" + long["category"] + "_kwh"
    return Batch(daily=long[["series", "day", "value"]])


def fetch_weather_forecast(c: Clients, s: Settings, start: date, end: date, today: date) -> Batch:
    """The 16-day forecast issued today. It cannot be fetched for past days, so start and end are
    ignored; the dataset keeps what each day's run archives."""
    return Batch(weather_forecast=c.meteo.forecast(today))


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

# Datasets the model can do without for a while. When one fails the run goes on: the features are
# then missing (NaN) for the newest days, which the trees treat as unknown. Weather and the ONI are
# here so that an outage of NOAA or Open-Meteo does not stop every forecast; the publication gate
# (gates.py) stops it only when their stored data is too old.
OPTIONAL_DATASETS = frozenset(
    {"xm_market", "xm_contracts", "xm_regional", "weather_forecast", "weather", "oni"}
)

DATASETS: dict[str, Fetcher] = {
    "xm_daily": fetch_xm_daily,
    "xm_price": fetch_xm_price,
    "xm_market": fetch_xm_market,
    "xm_contracts": fetch_xm_contracts,
    "xm_regional": fetch_xm_regional,
    "xm_generation": fetch_xm_generation,
    "xm_mix": fetch_xm_mix,
    "weather": fetch_weather,
    "weather_forecast": fetch_weather_forecast,
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
    # A normal update of a dataset takes seconds. If XM hangs, fail this dataset early so the others
    # and the next run are not starved. The budget is per 31-day window, so a gap after an outage
    # still fits; a backfill, and the first load of a dataset (which reads years), have no limit.
    if full or last is None:
        clients.xm.start_budget(None)
    else:
        windows = max(1, -(-((end - start).days + 1) // MAX_WINDOW_DAYS))
        clients.xm.start_budget(settings.xm_dataset_budget_s * windows)
    try:
        batch = DATASETS[name](clients, settings, start, end, today)
        if batch.is_empty:
            raise BatchValidationError("the source returned no data for the requested range")
        guards = STEP_GUARDS.get(name, ())
        if guards and not batch.daily.empty:
            names = [n for g in guards for n in g.series]
            anchors = db.last_values(engine, names, start, ANCHOR_MAX_AGE_DAYS)
            batch = guard_steps(batch, guards, anchors)
        required = REQUIRED_SERIES.get(name, ())
        if required:
            present = set(batch.daily["series"]) if not batch.daily.empty else set()
            missing = [n for n in required if n not in present]
            if missing:
                raise BatchValidationError(f"series missing from the batch: {', '.join(missing)}")
        days = []
        rows = 0
        if not batch.daily.empty:
            daily = validate_daily(batch.daily, continuous=batch.continuous, latest=end)
            rows += db.upsert_series_daily(engine, daily)
            days.append(newest_day_of(daily, required))
        if batch.entities is not None and not batch.entities.empty:
            entities = validate_entities(batch.entities)
            rows += db.upsert_entity_daily(engine, entities)
            if batch.catalog is not None:
                db.replace_entity_catalog(engine, batch.catalog)
            days.append(entities["day"].max())
        if batch.weather_forecast is not None and not batch.weather_forecast.empty:
            forecast = validate_weather_forecast(batch.weather_forecast)
            rows += db.archive_weather_forecast(engine, forecast)
            days.append(forecast["issued"].max())
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


def newest_complete_day(c: Clients, s: Settings, today: date, window_days: int = 7) -> date | None:
    """The newest day XM has published in full for both the price and the demand.

    It reads the last `window_days` through the same fetchers the pipeline uses, so a partial day
    (fewer than 24 hours) or a placeholder demand is dropped exactly as it is when training. The
    training needs both series, hence the earlier of the two days.
    """
    start, end = today - timedelta(days=window_days), today - timedelta(days=1)
    price = fetch_xm_price(c, s, start, end, today).daily
    demand = fetch_xm_daily(c, s, start, end, today).daily
    price_days = price.loc[price["series"] == "price_mean_cop_kwh", "day"]
    demand_days = demand.loc[demand["series"] == "demand_kwh", "day"]
    if price_days.empty or demand_days.empty:
        return None
    return pd.Timestamp(min(price_days.max(), demand_days.max())).date()


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
