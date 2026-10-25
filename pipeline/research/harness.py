"""Shared experiment harness: data, publication lags, origins, scoring and paired comparisons.

Every experiment reads the local snapshots (`data/history.csv`, `data/extra.csv`), forecasts from
development origins only, and is scored the same way as the production backtest. The reported
origins (2023-11 onwards) are not touched here; `REPORTED_FIRST` guards against it.

Publication lags: XM settles prices about three days after the day they belong to, so a forecast
made when the last settled price is day T is really made on day A = T + SETTLE_LAG. Series that
arrive faster (reservoirs, the programmed dispatch cost) are already known past T at that moment.
`known_through` states, per series, the last day usable at A. Nothing is assumed beyond it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

from voltia.features import TARGETS, TargetSpec, complete_daily, log_positive
from voltia.models import metrics
from voltia.models.backtest import (
    BacktestConfig,
    calibrate_online,
    select_origins,
)
from voltia.models.baselines import ets_forecast, seasonal_naive_quantiles

HERE = Path(__file__).parent
DATA = HERE / "data"
RESULTS = HERE / "results"

SETTLE_LAG = 3  # days between a price day and the day XM publishes its settled price
REPORTED_FIRST = pd.Timestamp("2023-11-21")  # first reported origin; experiments stay before it
DEV_FIRST = pd.Timestamp("2020-03-01")
DEV_STEP_DAYS = 30
N_WARMUP = 8

# Days after day D at which its value is published (A - lag is the last day known at A).
PUBLICATION_LAG: dict[str, int] = {
    "price_mean_cop_kwh": 3,
    "demand_kwh": 3,
    "max_offer": 3,
    "max_offer_max": 3,
    "price_tx1": 3,
    "price_tx1_max": 3,
    "exports_kwh": 3,
    "imports_kwh": 3,
    "scarcity_price": 3,
    "enficc_kwh": 3,
    "delta_nal": 3,
    "contract_price": 5,
    "contract_price_unreg": 5,
    "contract_price_unreg_max": 5,
    "reservoir_pct": 1,
    "reservoir_kwh": 1,
    "inflows_pct": 1,
    "inflows_kwh": 1,
    "spill_kwh": 1,
    "turbined_m3": 1,
    "reservoir_capacity_kwh": 1,
    # Programmed dispatch cost is published the day before the day it prices. The conservative
    # rule used for selection assumes it is usable only up to the day before A; the optimistic
    # one (lag 0) is reported separately.
    "dispatch_cost": 1,
    "dispatch_cost_max": 1,
}

QUANTILES = (0.1, 0.5, 0.9)


def load_data() -> pd.DataFrame:
    """History plus the extra XM series, one row per calendar day."""
    history = pd.read_csv(DATA / "history.csv", index_col="day", parse_dates=True)
    extra = pd.read_csv(DATA / "extra.csv", index_col="day", parse_dates=True)
    merged = history.join(extra, how="outer")
    return complete_daily(merged)


def known_through(name: str, as_of: pd.Timestamp, lag_overrides: dict[str, int] | None = None) -> pd.Timestamp:
    """Last day of series `name` that is usable on day `as_of`."""
    lags = {**PUBLICATION_LAG, **(lag_overrides or {})}
    return pd.Timestamp(as_of) - pd.Timedelta(days=lags.get(name, SETTLE_LAG))


def dev_origins(target: TargetSpec, first: pd.Timestamp = DEV_FIRST) -> list[pd.Timestamp]:
    """Origins `DEV_STEP_DAYS` apart from `first`, all of whose outcomes precede the reported ones."""
    last_allowed = REPORTED_FIRST - pd.Timedelta(days=target.horizon + 1)
    origins = []
    day = pd.Timestamp(first).as_unit("ns")
    while day <= last_allowed:
        origins.append(day)
        day += pd.Timedelta(days=DEV_STEP_DAYS)
    return origins


def assert_development(origins: list[pd.Timestamp], target: TargetSpec) -> None:
    """Stop an experiment that would score on days at or after the first reported origin."""
    last_outcome = max(origins) + pd.Timedelta(days=target.horizon)
    if last_outcome >= REPORTED_FIRST:
        raise ValueError(f"origin {max(origins).date()} reaches the reported period")


@dataclass(frozen=True)
class Baselines:
    """Baseline forecasts per (origin, h): seasonal naive and ETS, in level units."""

    rows: pd.DataFrame


def baseline_rows(
    data: pd.DataFrame, target: TargetSpec, origins: list[pd.Timestamp], cfg: BacktestConfig | None = None
) -> pd.DataFrame:
    """Seasonal naive and ETS forecasts for each origin, computed once and cached on disk."""
    cfg = cfg or BacktestConfig()
    series = data[target.name]
    frames = []
    for origin in origins:
        sn = seasonal_naive_quantiles(series, origin, target.horizon, cfg.sn_error_window_days)
        ets = ets_forecast(
            series, origin, target.horizon, target.name in cfg.log_targets, cfg.ets_window_days
        )
        frame = pd.DataFrame({"origin": origin, "h": np.arange(1, target.horizon + 1)})
        frame["day"] = origin + pd.to_timedelta(frame["h"], unit="D")
        for j, q in enumerate(("10", "50", "90")):
            frame[f"sn{q}"] = sn[:, j]
            frame[f"ets{q}"] = ets[:, j]
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def cached_baselines(data: pd.DataFrame, target: TargetSpec, origins: list[pd.Timestamp], tag: str) -> pd.DataFrame:
    path = DATA / f"baselines_{target.name}_{tag}.csv"
    if path.exists():
        cached = pd.read_csv(path, parse_dates=["origin", "day"])
        if set(cached["origin"].unique()) == set(origins):
            return cached
    rows = baseline_rows(data, target, origins)
    rows.to_csv(path, index=False)
    return rows


def finish_rows(
    pred: pd.DataFrame,
    data: pd.DataFrame,
    target: TargetSpec,
    baselines: pd.DataFrame,
    n_warmup: int = N_WARMUP,
    min_calibration_origins: int = 4,
) -> pd.DataFrame:
    """Attach actuals, scale, baselines and the online-calibrated columns to raw predictions.

    `pred` has one row per (origin, h) with q10_log, q50_log, q90_log (log of the target).
    """
    series = data[target.name]
    rows = pred.merge(baselines, on=["origin", "h", "day"], how="left", validate="one_to_one")
    rows["target"] = target.name
    rows["bucket"] = [target.bucket(int(h)) for h in rows["h"]]
    rows["y"] = series.reindex(pd.DatetimeIndex(rows["day"])).to_numpy()
    origins = sorted(rows["origin"].unique())
    rows["warmup"] = rows["origin"].isin(origins[:n_warmup])
    scale = {o: metrics.mase_scale(series.loc[:o]) for o in origins}
    rows["scale"] = rows["origin"].map(scale)
    for q in ("10", "50", "90"):
        rows[f"r{q}"] = np.exp(rows[f"q{q}_log"])
    return calibrate_online(rows, min_calibration_origins, target)


def _method(part: pd.DataFrame, prefix: str) -> dict[str, float]:
    y = part["y"].to_numpy()
    lo, mid, hi = (part[f"{prefix}{q}"].to_numpy() for q in ("10", "50", "90"))
    p10, p50, p90 = (
        metrics.pinball(y, q, a) for q, a in zip((lo, mid, hi), QUANTILES, strict=True)
    )
    return {
        "mape": metrics.mape(y, mid),
        "mase": metrics.mase(y, mid, part["scale"].to_numpy()),
        "pinball_p10": p10,
        "pinball_p50": p50,
        "pinball_p90": p90,
        "pinball_mean": (p10 + p50 + p90) / 3,
        "coverage": metrics.coverage(y, lo, hi),
        "winkler80": float(
            np.mean((hi - lo) + (2 / 0.2) * (np.maximum(lo - y, 0) + np.maximum(y - hi, 0)))
        ),
    }


def score(rows: pd.DataFrame, methods: dict[str, str] | None = None) -> dict[str, Any]:
    """Metrics for each method over the scored (non-warm-up, calibrated, observed) rows."""
    methods = methods or {"model": "m", "model_raw": "r", "seasonal_naive": "sn", "ets": "ets"}
    scored = rows[(~rows["warmup"]) & rows["calibrated"] & rows["y"].notna()]
    out: dict[str, Any] = {"n_rows": int(len(scored)), "n_origins": int(scored["origin"].nunique())}
    for name, prefix in methods.items():
        out[name] = _method(scored, prefix)
        out[name]["by_bucket"] = {
            b: {k: v for k, v in _method(p, prefix).items() if k in ("mase", "mape", "pinball_mean")}
            for b, p in scored.groupby("bucket")
        }
    return out


def per_origin(rows: pd.DataFrame, prefix: str, kind: str = "mase") -> pd.Series:
    scored = rows[(~rows["warmup"]) & rows["calibrated"] & rows["y"].notna()]
    values: dict[Any, float] = {}
    for origin, part in scored.groupby("origin"):
        y = part["y"].to_numpy()
        if kind == "mase":
            values[origin] = metrics.mase(y, part[f"{prefix}50"].to_numpy(), part["scale"].to_numpy())
        else:
            values[origin] = float(
                np.mean(
                    [
                        metrics.pinball(y, part[f"{prefix}{q}"].to_numpy(), a)
                        for q, a in zip(("10", "50", "90"), QUANTILES, strict=True)
                    ]
                )
            )
    return pd.Series(values).sort_index()


def paired(rows: pd.DataFrame, a: str, b: str, kind: str = "mase", n_boot: int = 4000, seed: int = 7) -> dict[str, float]:
    """Mean per-origin difference (a minus b; negative favours a), bootstrap CI and Wilcoxon p."""
    da, db = per_origin(rows, a, kind), per_origin(rows, b, kind)
    diff = (da - db).dropna().to_numpy()
    rng = np.random.default_rng(seed)
    means = rng.choice(diff, size=(n_boot, len(diff)), replace=True).mean(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    try:
        p = float(wilcoxon(diff).pvalue)
    except ValueError:
        p = float("nan")
    return {
        "mean_diff": float(diff.mean()),
        "ci_low": float(lo),
        "ci_high": float(hi),
        "wins": int((diff < 0).sum()),
        "origins": int(len(diff)),
        "wilcoxon_p": p,
    }


def rounded(value: Any, digits: int = 4) -> Any:
    if isinstance(value, dict):
        return {k: rounded(v, digits) for k, v in value.items()}
    if isinstance(value, float):
        return round(value, digits)
    return value


def save_result(name: str, target: str, payload: dict[str, Any]) -> Path:
    path = RESULTS / target / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rounded(payload), indent=2, sort_keys=True), encoding="utf-8")
    return path


Forecaster = Callable[[pd.DataFrame, pd.Timestamp], pd.DataFrame]

__all__ = [
    "TARGETS",
    "Forecaster",
    "load_data",
    "dev_origins",
    "select_origins",
    "log_positive",
]
