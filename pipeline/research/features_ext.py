"""Experimental feature blocks for the price model, built on the publication lags in harness.py.

For a row (origin T, horizon h) the forecast is made on day A = T + SETTLE_LAG. A block may use a
series up to `A - lag` and nothing later; `test_features_ext.py` mutates everything past that day and
asserts the rows do not change. All values are relative to the 7-day mean of log price at T
(`ref_log`), like the production features, so the level of the market does not leak into them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from harness import PUBLICATION_LAG, REGIONS, SETTLE_LAG
from voltia.features import log_positive

BLOCKS = ("dispatch", "offers", "contracts", "hydro_now", "trade", "nowcast")
PHASE_B_BLOCKS = ("regional", "profile", "restrictions", "availability")

FEATURES: dict[str, list[str]] = {
    "dispatch": [
        "dc_target_rel",
        "dc_known_mean_rel",
        "dc_mean7_rel",
        "dc_basis14",
        "dc_corrected_target_rel",
        "dc_chg3",
    ],
    "offers": ["offer_rel7", "offer_max_gap7", "tx1_gap7"],
    "contracts": ["contract_rel", "scarcity_rel", "contract_unreg_rel", "price_contract_gap28"],
    "hydro_now": [
        "reservoir_now_chg",
        "inflows_now_chg",
        "spill7",
        "spill_chg28",
        "turbined_rel90",
        "reservoir_capacity_share",
    ],
    "trade": ["exports7", "imports7", "net_exports7"],
    # Estimated price level on the newest days already priced by the dispatch: dispatch cost plus
    # the recent gap between settled price and dispatch cost.
    "nowcast": ["dc_corr_latest_rel", "dc_corr_mean3_rel"],
    # Hydrology by XM region: share of the region's usable capacity that is full, and its inflows
    # (last 7 days) against their historical mean; the spread says where the water is.
    "regional": [
        *[f"reg_level_{r}" for r in REGIONS],
        *[f"reg_inflow_{r}" for r in REGIONS],
        "reg_level_spread",
        "reg_inflow_spread",
    ],
    # Shape of the hourly price over the last 7 settled days.
    "profile": ["peak_gap7", "night_gap7", "hour_std7", "hour_min_gap7"],
    # Cost of the constraints (restrictions) against its own 90-day mean.
    "restrictions": ["restr_plain_rel90", "restr_relief_rel90"],
    # Generation capacity that was available (real and declared) against its own 90-day mean, the
    # share of declared thermal capacity that was not really available, and the cost of generating
    # out of merit order for security.
    "availability": [
        "thermal_real_rel90",
        "thermal_decl_rel90",
        "thermal_outage7",
        "hydro_real_rel90",
        "margin_rel90",
        "oom_thermal_rel90",
    ],
}


def block_names(blocks: tuple[str, ...] | list[str]) -> list[str]:
    return [name for block in blocks for name in FEATURES[block]]


def _k(name: str, lags: dict[str, int]) -> int:
    """How many days past the origin the series is already known (negative: published later)."""
    return SETTLE_LAG - lags.get(name, SETTLE_LAG)


def _latest(series: pd.Series, name: str, lags: dict[str, int]) -> pd.Series:
    """Value on the newest day known at A, aligned to the origin T."""
    return series.shift(-_k(name, lags))


def _roll(series: pd.Series, window: int, name: str, lags: dict[str, int], how: str = "mean") -> pd.Series:
    """Rolling statistic ending on the newest day known at A, aligned to the origin T."""
    rolled = series.rolling(window, min_periods=max(1, int(window * 0.7)))
    out = rolled.mean() if how == "mean" else rolled.sum()
    return out.shift(-_k(name, lags))


def origin_blocks(data: pd.DataFrame, lags: dict[str, int] | None = None) -> pd.DataFrame:
    """Origin-level features (one row per origin day) for every block, from the full frame."""
    lags = {**PUBLICATION_LAG, **(lags or {})}
    price = log_positive(data["price_mean_cop_kwh"])
    ref = price.rolling(7, min_periods=5).mean()
    out: dict[str, pd.Series] = {}

    dc = log_positive(data["dispatch_cost"])
    k_dc = _k("dispatch_cost", lags)
    basis14 = (price - dc).rolling(14, min_periods=10).mean()  # price minus dispatch, known at T
    out["dc_basis14"] = basis14
    dc_known = pd.concat([dc.shift(-j) for j in range(1, max(k_dc, 0) + 1)], axis=1)
    out["dc_known_mean_rel"] = (dc_known.mean(axis=1) if k_dc > 0 else pd.Series(np.nan, index=data.index)) - ref
    out["dc_mean7_rel"] = _roll(dc, 7, "dispatch_cost", lags) - ref
    out["dc_chg3"] = dc.shift(-k_dc) - dc.shift(3 - k_dc)  # newest known day against three days before it

    offers = log_positive(data["max_offer"])
    offers_max = log_positive(data["max_offer_max"])
    tx1 = log_positive(data["price_tx1"])
    out["offer_rel7"] = _roll(offers, 7, "max_offer", lags) - ref
    out["offer_max_gap7"] = _roll(offers_max - offers, 7, "max_offer", lags)
    out["tx1_gap7"] = _roll(tx1 - price, 7, "price_tx1", lags)

    contract = log_positive(data["contract_price"])
    scarcity = log_positive(data["scarcity_price"])
    contract_unreg = log_positive(data["contract_price_unreg"])
    out["contract_rel"] = _latest(contract, "contract_price", lags) - ref
    out["scarcity_rel"] = _latest(scarcity, "scarcity_price", lags) - ref
    out["contract_unreg_rel"] = _latest(contract_unreg, "contract_price_unreg", lags) - ref
    out["price_contract_gap28"] = _roll(price, 28, "price_mean_cop_kwh", lags) - _roll(
        contract, 28, "contract_price", lags
    )

    reservoir = data["reservoir_pct"].astype(float)
    inflows = data["inflows_pct"].astype(float)
    out["reservoir_now_chg"] = _latest(reservoir, "reservoir_pct", lags) - reservoir
    out["inflows_now_chg"] = _roll(inflows, 3, "inflows_pct", lags) - _roll(inflows, 3, "price_mean_cop_kwh", lags)
    spill = data["spill_kwh"].fillna(0.0).astype(float) / 1e6
    out["spill7"] = _roll(spill, 7, "spill_kwh", lags)
    out["spill_chg28"] = _roll(spill, 7, "spill_kwh", lags) - _roll(spill, 28, "spill_kwh", lags)
    turbined = log_positive(data["turbined_m3"])
    out["turbined_rel90"] = _roll(turbined, 7, "turbined_m3", lags) - _roll(turbined, 90, "turbined_m3", lags)
    capacity = data["reservoir_capacity_kwh"].astype(float)
    reservoir_kwh = data["reservoir_kwh"].astype(float)
    out["reservoir_capacity_share"] = _latest(reservoir_kwh / capacity, "reservoir_capacity_kwh", lags)

    exports = data["exports_kwh"].fillna(0.0).astype(float) / 1e6
    imports = data["imports_kwh"].fillna(0.0).astype(float) / 1e6
    out["exports7"] = _roll(exports, 7, "exports_kwh", lags)
    out["imports7"] = _roll(imports, 7, "imports_kwh", lags)
    out["net_exports7"] = out["exports7"] - out["imports7"]

    out["dc_corr_latest_rel"] = dc.shift(-k_dc) + basis14 - ref
    out["dc_corr_mean3_rel"] = dc.rolling(3, min_periods=2).mean().shift(-k_dc) + basis14 - ref

    _regional_blocks(data, out, lags)
    _profile_blocks(data, out, lags, price)

    frame = pd.DataFrame(out, index=data.index)
    frame["_ref"] = ref
    return frame


def _col(data: pd.DataFrame, name: str) -> pd.Series:
    return data[name].astype(float) if name in data.columns else pd.Series(np.nan, index=data.index)


def _regional_blocks(data: pd.DataFrame, out: dict[str, pd.Series], lags: dict[str, int]) -> None:
    levels, inflows = [], []
    for region in REGIONS:
        volume = _col(data, f"reg_reservoir_kwh_{region}")
        capacity = _col(data, f"reg_reservoir_capacity_kwh_{region}")
        flow = _col(data, f"reg_inflows_kwh_{region}")
        mean = _col(data, f"reg_inflows_hist_mean_kwh_{region}")
        level = _latest(volume / capacity.where(capacity > 0), f"reg_reservoir_kwh_{region}", lags)
        ratio = np.log(
            _roll(flow, 7, f"reg_inflows_kwh_{region}", lags).clip(lower=1.0)
            / _roll(mean, 7, f"reg_inflows_hist_mean_kwh_{region}", lags).clip(lower=1.0)
        )
        out[f"reg_level_{region}"] = level
        out[f"reg_inflow_{region}"] = ratio
        levels.append(level)
        inflows.append(ratio)
    out["reg_level_spread"] = pd.concat(levels, axis=1).max(axis=1) - pd.concat(levels, axis=1).min(axis=1)
    out["reg_inflow_spread"] = pd.concat(inflows, axis=1).max(axis=1) - pd.concat(inflows, axis=1).min(axis=1)


def _profile_blocks(
    data: pd.DataFrame, out: dict[str, pd.Series], lags: dict[str, int], price: pd.Series
) -> None:
    peak = log_positive(_col(data, "price_peak"))
    night = log_positive(_col(data, "price_night"))
    low = log_positive(_col(data, "price_min"))
    std = _col(data, "price_std")
    mean = np.exp(price)
    out["peak_gap7"] = _roll(peak - price, 7, "price_peak", lags)
    out["night_gap7"] = _roll(night - price, 7, "price_night", lags)
    out["hour_std7"] = _roll(std / mean, 7, "price_std", lags)
    out["hour_min_gap7"] = _roll(low - price, 7, "price_min", lags)
    plain = log_positive(_col(data, "restr_plain_cop"))
    relief = log_positive(_col(data, "restr_relief_cop"))
    thermal_real = _col(data, "dispo_real_thermal")
    thermal_decl = _col(data, "dispo_decl_thermal")
    hydro_real = _col(data, "dispo_real_hydro")
    demand = _col(data, "demand_kwh")
    out["thermal_real_rel90"] = np.log(_roll(thermal_real, 7, "dispo_real_thermal", lags)) - np.log(
        _roll(thermal_real, 90, "dispo_real_thermal", lags)
    )
    out["thermal_decl_rel90"] = np.log(_roll(thermal_decl, 7, "dispo_decl_thermal", lags)) - np.log(
        _roll(thermal_decl, 90, "dispo_decl_thermal", lags)
    )
    out["thermal_outage7"] = 1 - _roll(thermal_real, 7, "dispo_real_thermal", lags) / _roll(
        thermal_decl, 7, "dispo_decl_thermal", lags
    )
    out["hydro_real_rel90"] = np.log(_roll(hydro_real, 7, "dispo_real_hydro", lags)) - np.log(
        _roll(hydro_real, 90, "dispo_real_hydro", lags)
    )
    margin = np.log((thermal_real + hydro_real) / demand)
    out["margin_rel90"] = _roll(margin, 7, "dispo_real_thermal", lags) - _roll(
        margin, 90, "dispo_real_thermal", lags
    )
    oom = log_positive(_col(data, "out_of_merit_thermal"))
    out["oom_thermal_rel90"] = _roll(oom, 7, "out_of_merit_thermal", lags) - _roll(
        oom, 90, "out_of_merit_thermal", lags
    )
    out["restr_plain_rel90"] = _roll(plain, 7, "restr_plain_cop", lags) - _roll(plain, 90, "restr_plain_cop", lags)
    out["restr_relief_rel90"] = _roll(relief, 7, "restr_relief_cop", lags) - _roll(relief, 90, "restr_relief_cop", lags)


def add_blocks(
    table: pd.DataFrame,
    data: pd.DataFrame,
    blocks: tuple[str, ...] | list[str],
    lags: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Columns of the chosen blocks for the rows of a production feature table (origin, h, day)."""
    lags = {**PUBLICATION_LAG, **(lags or {})}
    base = origin_blocks(data, lags)
    wanted = block_names(blocks)
    per_row = {"dc_target_rel", "dc_corrected_target_rel"}
    present = [n for n in wanted if n not in per_row]
    out = base.reindex(pd.DatetimeIndex(table["origin"]))[[*present, "_ref"]].reset_index(drop=True)
    if "dispatch" in blocks:
        dc = log_positive(data["dispatch_cost"])
        k_dc = _k("dispatch_cost", lags)
        h = table["h"].to_numpy()
        day_values = dc.reindex(pd.DatetimeIndex(table["day"])).to_numpy()
        known = h <= k_dc
        out["dc_target_rel"] = np.where(known, day_values - out["_ref"].to_numpy(), np.nan)
        out["dc_corrected_target_rel"] = np.where(
            known, day_values + out["dc_basis14"].to_numpy() - out["_ref"].to_numpy(), np.nan
        )
    return out[wanted]
