"""Features for the direct multi-horizon forecasters (one row per origin T and horizon h).

A row for origin T uses only what was published by the day the forecast is made, plus calendar
facts about the target day T + h (weekday, holidays, long weekends), which are known in advance.
XM settles the price about three days after its day, so the forecast of origin T (the last settled
day) is made on day A = T + SETTLE_LAG_DAYS; hydrology and the programmed dispatch cost are
published faster and are already known past T (PUBLICATION_LAG_DAYS). Nothing later than
A - lag is read for a series. `build_features` makes this explicit by truncating the history at A;
the vectorised `feature_table` used for training is tested to give bit-identical rows.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

import holidays
import numpy as np
import pandas as pd
from dateutil.easter import easter

# ONI for the season centred on month M is stored on day 1 of M and needs data through M + 1,
# so NOAA publishes it early in M + 2. 75 days after the stored date is a safe availability.
ONI_PUBLICATION_LAG_DAYS = 75
HOLIDAY_DISTANCE_CAP = 14
YEAR = 364  # 52 weeks: keeps the weekday aligned

# Days between the day a forecast origin T is settled and the day the forecast is made.
SETTLE_LAG_DAYS = 3
# Days after its own day at which XM publishes a value; series not listed are read only up to T.
# The dispatch cost is programmed the day before it applies; one day of margin is kept.
PUBLICATION_LAG_DAYS: dict[str, int] = {
    "dispatch_cost": 1,
    "reservoir_pct": 1,
    "reservoir_kwh": 1,
    "reservoir_capacity_kwh": 1,
    "inflows_pct": 1,
    "spill_kwh": 1,
    "turbined_m3": 1,
    "scarcity_price": 3,
    "contract_price": 5,
    "contract_price_unreg": 5,
}


def days_known_past_origin(series: str) -> int:
    """Days past the origin of the newest usable value of `series` (negative: before it)."""
    return SETTLE_LAG_DAYS - PUBLICATION_LAG_DAYS.get(series, SETTLE_LAG_DAYS)


@dataclass(frozen=True)
class TargetSpec:
    """A forecast target: the series, its horizon and the horizon buckets used for reporting."""

    name: str
    horizon: int
    buckets: tuple[tuple[int, int], ...]

    @property
    def horizons(self) -> list[int]:
        return list(range(1, self.horizon + 1))

    def bucket(self, h: int) -> str:
        for lo, hi in self.buckets:
            if lo <= h <= hi:
                return f"{lo}-{hi}"
        raise ValueError(f"horizon {h} outside 1..{self.horizon}")


TARGETS: dict[str, TargetSpec] = {
    "demand_kwh": TargetSpec("demand_kwh", 30, ((1, 7), (8, 14), (15, 30))),
    "price_mean_cop_kwh": TargetSpec("price_mean_cop_kwh", 14, ((1, 3), (4, 7), (8, 14))),
}

CALENDAR_FEATURES = [
    "dow",
    "month",
    "doy_sin",
    "doy_cos",
    "is_holiday",
    "is_nonworking",
    "in_long_weekend",
    "holy_week",
    "year_end",
    "christmas_new_year",
    "days_to_holiday",
    "days_from_holiday",
]
HORIZON_FEATURES = [
    "h",
    "same_dow_last_rel",
    "same_dow_mean4_rel",
    "last_year_shape",
    "ref_day_nonworking",
    "last_year_day_nonworking",
]
OWN_FEATURES = ["level_last_rel", "level_prev_rel", "mom_7_28", "mom_28_91", "yoy_28", "vol_28"]
EXOGENOUS_FEATURES = [
    "reservoir_pct",
    "reservoir_chg7",
    "reservoir_chg30",
    "reservoir_yoy",
    "inflows_pct_mean7",
    "inflows_pct_mean30",
    "inflows_pct_mean90",
    "thermal_share_7",
    "renewable_share_28",
    "temp_mean7",
    "temp_mean30_yoy",
    "precip_sum30",
    "oni_known",
    "oni_chg3",
]
CROSS_FEATURES = {
    "demand_kwh": ["price_level_yoy_28"],
    "price_mean_cop_kwh": ["demand_yoy_28", "price_spike_7"],
}
# Market state read past the origin (see PUBLICATION_LAG_DAYS), relative to the 7-day mean log
# price:
# the programmed dispatch cost of the days XM has not settled yet, contract and scarcity prices,
# and the newest hydrology. `dc_target_rel` and `dc_corrected_target_rel` depend on the horizon.
MARKET_FEATURES = {
    "price_mean_cop_kwh": [
        "dc_target_rel",
        "dc_known_mean_rel",
        "dc_mean7_rel",
        "dc_basis14",
        "dc_corrected_target_rel",
        "dc_chg3",
        "contract_rel",
        "scarcity_rel",
        "contract_unreg_rel",
        "price_contract_gap28",
        "reservoir_now_chg",
        "inflows_now_chg",
        "spill7",
        "spill_chg28",
        "turbined_rel90",
        "reservoir_capacity_share",
    ],
}
META_COLUMNS = ["origin", "day", "ref_log", "sn_log", "last_log"]


def feature_names(target: str) -> list[str]:
    """Model input columns for a target, in a fixed order."""
    return [
        *HORIZON_FEATURES,
        *CALENDAR_FEATURES,
        *OWN_FEATURES,
        *CROSS_FEATURES[target],
        *EXOGENOUS_FEATURES,
        *MARKET_FEATURES.get(target, []),
    ]


@lru_cache(maxsize=8)
def _holiday_dates(first_year: int, last_year: int) -> frozenset[date]:
    years = list(range(first_year, last_year + 1))
    return frozenset(holidays.country_holidays("CO", years=years).keys())


def calendar_frame(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Calendar features for every day in [start, end], Colombian public holidays included.

    Long weekends ("puentes") are runs of three or more consecutive non-working days, which in
    Colombia are mostly created by the Emiliani law moving holidays to Monday.
    """
    pad = pd.Timedelta(days=40)
    days = pd.date_range(start - pad, end + pad, freq="D", unit="ns")
    hol = _holiday_dates(days[0].year, days[-1].year)
    is_hol = np.array([d.date() in hol for d in days])
    nonwork = is_hol | (days.day_of_week >= 5)

    run_id = np.cumsum(np.r_[True, nonwork[1:] != nonwork[:-1]])
    run_len = pd.Series(run_id).map(pd.Series(run_id).value_counts()).to_numpy()
    long_weekend = nonwork & (run_len >= 3)

    holy = np.zeros(len(days), dtype=bool)
    for year in range(days[0].year, days[-1].year + 1):
        sunday = pd.Timestamp(easter(year))
        holy |= (days >= sunday - pd.Timedelta(days=7)) & (days <= sunday)

    hol_days = days[is_hol].to_numpy()
    values = days.to_numpy()
    nxt = np.searchsorted(hol_days, values, side="left")
    prv = np.searchsorted(hol_days, values, side="right") - 1
    big = np.timedelta64(10_000, "D")
    to_next = np.where(nxt < len(hol_days), hol_days[np.minimum(nxt, len(hol_days) - 1)], values)
    to_next_days = np.where(nxt < len(hol_days), (to_next - values), big)
    from_prev = np.where(prv >= 0, values - hol_days[np.maximum(prv, 0)], big)

    doy = days.day_of_year.to_numpy()
    frame = pd.DataFrame(
        {
            "dow": days.day_of_week.to_numpy(),
            "month": days.month.to_numpy(),
            "doy_sin": np.sin(2 * np.pi * doy / 365.25),
            "doy_cos": np.cos(2 * np.pi * doy / 365.25),
            "is_holiday": is_hol.astype(float),
            "is_nonworking": nonwork.astype(float),
            "in_long_weekend": long_weekend.astype(float),
            "holy_week": holy.astype(float),
            "year_end": (
                ((days.month == 12) & (days.day >= 24)) | ((days.month == 1) & (days.day <= 6))
            ).astype(float),
            "christmas_new_year": (
                ((days.month == 12) & np.isin(days.day, [24, 25, 31]))
                | ((days.month == 1) & (days.day == 1))
            ).astype(float),
            "days_to_holiday": np.minimum(
                to_next_days.astype("timedelta64[D]").astype(int), HOLIDAY_DISTANCE_CAP
            ),
            "days_from_holiday": np.minimum(
                from_prev.astype("timedelta64[D]").astype(int), HOLIDAY_DISTANCE_CAP
            ),
        },
        index=days,
    )
    return frame.loc[start:end]


def complete_daily(history: pd.DataFrame) -> pd.DataFrame:
    """Reindex to one row per calendar day (nanosecond DatetimeIndex), missing days as NaN."""
    index = pd.DatetimeIndex(history.index).as_unit("ns")
    frame = history.copy()
    frame.index = index
    full = pd.date_range(index.min(), index.max(), freq="D", unit="ns")
    return frame.reindex(full)


def _col(hist: pd.DataFrame, name: str) -> pd.Series:
    if name in hist.columns:
        return hist[name].astype(float)
    return pd.Series(np.nan, index=hist.index)


def log_positive(series: pd.Series) -> pd.Series:
    """Natural log, NaN where the value is missing or not positive."""
    values = series.astype(float)
    return pd.Series(np.log(values.where(values > 0)), index=series.index)


def _mean(s: pd.Series, window: int) -> pd.Series:
    return s.rolling(window, min_periods=max(1, int(window * 0.75))).mean()


def oni_known(hist: pd.DataFrame) -> pd.Series:
    """Latest ONI value already published on each day (see ONI_PUBLICATION_LAG_DAYS)."""
    oni = _col(hist, "oni").dropna()
    if oni.empty:
        return pd.Series(np.nan, index=hist.index)
    available = pd.Series(
        oni.to_numpy(), index=oni.index + pd.Timedelta(days=ONI_PUBLICATION_LAG_DAYS)
    )
    available = available[available.index <= hist.index[-1]]
    union = hist.index.union(available.index)
    known: pd.Series = available.reindex(union).ffill().reindex(hist.index)
    return known


def _newest(series: pd.Series, name: str) -> pd.Series:
    """Value of `series` on the newest day usable at the forecast date, aligned to the origin."""
    return series.shift(-days_known_past_origin(name))


def _rolling_known(series: pd.Series, window: int, name: str, how: str = "mean") -> pd.Series:
    """Rolling mean or sum ending on the newest usable day of `name`, aligned to the origin."""
    rolled = series.rolling(window, min_periods=max(1, int(window * 0.7)))
    return (rolled.mean() if how == "mean" else rolled.sum()).shift(-days_known_past_origin(name))


def market_features(hist: pd.DataFrame, price: pd.Series, ref: pd.Series) -> dict[str, pd.Series]:
    """Origin-level market features of the price model; NaN where a series is not loaded yet."""
    out: dict[str, pd.Series] = {}
    dc = log_positive(_col(hist, "dispatch_cost"))
    k_dc = days_known_past_origin("dispatch_cost")
    basis = (price - dc).rolling(14, min_periods=10).mean()  # settled price minus dispatch cost
    out["dc_basis14"] = basis
    ahead = [dc.shift(-j) for j in range(1, k_dc + 1)]
    known_mean = (
        pd.concat(ahead, axis=1).mean(axis=1) if ahead else pd.Series(np.nan, index=dc.index)
    )
    out["dc_known_mean_rel"] = known_mean - ref
    out["dc_mean7_rel"] = _rolling_known(dc, 7, "dispatch_cost") - ref
    out["dc_chg3"] = dc.shift(-k_dc) - dc.shift(3 - k_dc)

    contract = log_positive(_col(hist, "contract_price"))
    scarcity = log_positive(_col(hist, "scarcity_price"))
    contract_unreg = log_positive(_col(hist, "contract_price_unreg"))
    out["contract_rel"] = _newest(contract, "contract_price") - ref
    out["scarcity_rel"] = _newest(scarcity, "scarcity_price") - ref
    out["contract_unreg_rel"] = _newest(contract_unreg, "contract_price_unreg") - ref
    out["price_contract_gap28"] = _rolling_known(price, 28, "price_mean_cop_kwh") - _rolling_known(
        contract, 28, "contract_price"
    )

    reservoir = _col(hist, "reservoir_pct")
    inflows = _col(hist, "inflows_pct")
    out["reservoir_now_chg"] = _newest(reservoir, "reservoir_pct") - reservoir
    out["inflows_now_chg"] = _rolling_known(inflows, 3, "inflows_pct") - _rolling_known(
        inflows, 3, "price_mean_cop_kwh"
    )
    raw_spill = _col(hist, "spill_kwh")
    last_spill = raw_spill.last_valid_index()
    # Zero-fill the days XM listed no spilling for, but not the days after the newest stored one.
    spill = (
        raw_spill
        if last_spill is None
        else raw_spill.where(raw_spill.index > last_spill, raw_spill.fillna(0.0))
    ) / 1e6
    out["spill7"] = _rolling_known(spill, 7, "spill_kwh")
    out["spill_chg28"] = out["spill7"] - _rolling_known(spill, 28, "spill_kwh")
    turbined = log_positive(_col(hist, "turbined_m3"))
    out["turbined_rel90"] = _rolling_known(turbined, 7, "turbined_m3") - _rolling_known(
        turbined, 90, "turbined_m3"
    )
    capacity_share = _col(hist, "reservoir_kwh") / _col(hist, "reservoir_capacity_kwh")
    out["reservoir_capacity_share"] = _newest(capacity_share, "reservoir_capacity_kwh")
    return out


def origin_features(hist: pd.DataFrame, target: str) -> pd.DataFrame:
    """Features that depend only on the origin day. `hist` must be a complete daily frame."""
    y = log_positive(hist[target])
    ref = _mean(y, 7)
    m28 = _mean(y, 28)
    m91 = _mean(y, 91)
    out: dict[str, pd.Series] = {
        "ref_log": ref,
        "level_last_rel": y - ref,
        "level_prev_rel": y.shift(1) - ref,
        "mom_7_28": ref - m28,
        "mom_28_91": m28 - m91,
        "yoy_28": m28 - m28.shift(YEAR),
        "vol_28": y.diff().rolling(28, min_periods=21).std(),
    }

    demand = log_positive(_col(hist, "demand_kwh"))
    price = log_positive(_col(hist, "price_mean_cop_kwh"))
    price_max = log_positive(_col(hist, "price_max_cop_kwh"))
    if target == "demand_kwh":
        price28 = _mean(price, 28)
        out["price_level_yoy_28"] = price28 - price28.shift(YEAR)
    else:
        demand28 = _mean(demand, 28)
        out["demand_yoy_28"] = demand28 - demand28.shift(YEAR)
        out["price_spike_7"] = _mean(price_max - price, 7)

    reservoir = _col(hist, "reservoir_pct")
    inflows = _col(hist, "inflows_pct")
    total = _col(hist, "gen_total_kwh")
    thermal = _col(hist, "gen_thermal_kwh")
    renewable = _col(hist, "gen_solar_kwh") + _col(hist, "gen_wind_kwh")
    temp = _col(hist, "weather_temp_c")
    temp30 = _mean(temp, 30)
    oni = oni_known(hist)
    out.update(
        {
            "reservoir_pct": reservoir,
            "reservoir_chg7": reservoir - reservoir.shift(7),
            "reservoir_chg30": reservoir - reservoir.shift(30),
            "reservoir_yoy": reservoir - reservoir.shift(YEAR),
            "inflows_pct_mean7": _mean(inflows, 7),
            "inflows_pct_mean30": _mean(inflows, 30),
            "inflows_pct_mean90": _mean(inflows, 90),
            "thermal_share_7": thermal.rolling(7, min_periods=5).sum()
            / total.rolling(7, min_periods=5).sum(),
            "renewable_share_28": renewable.rolling(28, min_periods=21).sum()
            / total.rolling(28, min_periods=21).sum(),
            "temp_mean7": _mean(temp, 7),
            "temp_mean30_yoy": temp30 - temp30.shift(YEAR),
            "precip_sum30": _col(hist, "weather_precip_mm").rolling(30, min_periods=23).sum(),
            "oni_known": oni,
            "oni_chg3": oni - oni.shift(91),
        }
    )
    if target in MARKET_FEATURES:
        out.update(market_features(hist, price, ref))
    return pd.DataFrame(out, index=hist.index)


def _row_mean(arrays: list[np.ndarray]) -> np.ndarray:
    stack = np.vstack(arrays)
    count = (~np.isnan(stack)).sum(axis=0)
    total = np.nansum(stack, axis=0)
    return np.where(count > 0, total / np.maximum(count, 1), np.nan)


def feature_table(
    history: pd.DataFrame,
    target: str,
    horizons: Sequence[int],
    origins: Iterable[pd.Timestamp] | None = None,
) -> pd.DataFrame:
    """Rows (origin, h) with META_COLUMNS and the features of `target`, for every origin.

    Every rolling window ends at the origin, so a row never sees days after its origin.
    """
    columns = [*META_COLUMNS, *feature_names(target)]
    hist = complete_daily(history)
    base = origin_features(hist, target)
    ref_all = base["ref_log"]
    y = log_positive(hist[target])
    if origins is not None:
        wanted = pd.DatetimeIndex(list(origins)).as_unit("ns")
        base = base.loc[base.index.intersection(wanted)]
    if base.empty:
        return pd.DataFrame(columns=columns)
    index = pd.DatetimeIndex(base.index)
    cal = calendar_frame(
        hist.index[0] - pd.Timedelta(days=YEAR), index[-1] + pd.Timedelta(days=max(horizons))
    )
    ref = base["ref_log"].to_numpy()
    last_log = y.reindex(index).to_numpy()
    ref_last_year = ref_all.reindex(index - pd.Timedelta(days=YEAR)).to_numpy()
    dispatch = log_positive(_col(hist, "dispatch_cost"))
    frames = []
    for h in horizons:
        k = (-h) % 7  # lag of the same weekday in the last observed week
        same_dow = [y.reindex(index - pd.Timedelta(days=k + 7 * j)).to_numpy() for j in range(4)]
        day = index + pd.Timedelta(days=h)
        frame = base.copy()
        frame.insert(0, "origin", index)
        frame.insert(1, "h", h)
        frame.insert(2, "day", day)
        frame["sn_log"] = same_dow[0]
        frame["last_log"] = last_log
        frame["same_dow_last_rel"] = same_dow[0] - ref
        frame["same_dow_mean4_rel"] = _row_mean(same_dow) - ref
        frame["last_year_shape"] = (
            y.reindex(day - pd.Timedelta(days=YEAR)).to_numpy() - ref_last_year
        )
        frame["ref_day_nonworking"] = (
            cal["is_nonworking"].reindex(index - pd.Timedelta(days=k)).to_numpy()
        )
        frame["last_year_day_nonworking"] = (
            cal["is_nonworking"].reindex(day - pd.Timedelta(days=YEAR)).to_numpy()
        )
        target_cal = cal.reindex(day)
        for name in CALENDAR_FEATURES:
            frame[name] = target_cal[name].to_numpy()
        if target in MARKET_FEATURES:
            known = h <= days_known_past_origin("dispatch_cost")
            at_day = dispatch.reindex(day).to_numpy()
            frame["dc_target_rel"] = np.where(known, at_day - ref, np.nan)
            frame["dc_corrected_target_rel"] = np.where(
                known, at_day + base["dc_basis14"].to_numpy() - ref, np.nan
            )
        frames.append(frame)
    table = pd.concat(frames, ignore_index=True)
    table = table.sort_values(["origin", "h"], kind="stable").reset_index(drop=True)
    return table[columns]


def build_features(
    history: pd.DataFrame, origin: pd.Timestamp, horizons: Sequence[int], target: str
) -> pd.DataFrame:
    """Feature rows for one origin, computed from `history` truncated at the forecast date.

    The forecast date is the origin plus SETTLE_LAG_DAYS: later days are cut, and each series is
    read only up to the day it is published by then.
    """
    origin = pd.Timestamp(origin).as_unit("ns")
    hist = complete_daily(history)
    if origin not in hist.index:
        raise ValueError(f"history does not reach the origin {origin.date()}")
    seen = hist.loc[: origin + pd.Timedelta(days=SETTLE_LAG_DAYS)]
    return feature_table(seen, target, horizons, origins=[origin])


def attach_target(table: pd.DataFrame, history: pd.DataFrame, target: str) -> pd.Series:
    """Log of the observed target on each row's target day (NaN when not observed)."""
    y = log_positive(complete_daily(history)[target])
    return pd.Series(y.reindex(pd.DatetimeIndex(table["day"])).to_numpy(), index=table.index)
