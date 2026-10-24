"""Rolling-origin backtest with an expanding window and retraining at every origin (ADR 0004).

Each origin trains on rows whose target day is on or before the origin, forecasts the next
`horizon` days and scores the model next to the baselines. Intervals are then calibrated
online: an origin only uses conformity scores of earlier origins whose outcomes were already
observed at that origin. Warm-up origins only seed the calibration and are not reported.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd
import structlog
from scipy.stats import wilcoxon

from voltia.features import TargetSpec, attach_target, complete_daily, feature_names, feature_table
from voltia.models import metrics
from voltia.models.baselines import ets_forecast, seasonal_naive_quantiles
from voltia.models.calibration import Offset, apply_offset, conformal_offset
from voltia.models.gbm import QUANTILES, GBMParams, fit_quantiles, predict_quantiles

log = structlog.get_logger()

Reference = Literal["level7", "seasonal_naive", "last"]
METHODS = ("model", "model_raw", "seasonal_naive", "ets")
_COLS = {"model": "m", "model_raw": "r", "seasonal_naive": "sn", "ets": "ets"}


@dataclass(frozen=True)
class ModelConfig:
    """How a target is transformed before fitting: log(y) minus a reference known at origin."""

    reference: Reference = "level7"
    params: GBMParams = field(default_factory=GBMParams)


@dataclass(frozen=True)
class BacktestConfig:
    n_origins: int = 24
    n_warmup: int = 8
    step_days: int = 45
    min_calibration_origins: int = 4
    ets_window_days: int = 1092
    sn_error_window_days: int = 728
    log_targets: tuple[str, ...] = ("price_mean_cop_kwh",)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Prepared:
    """Feature table for every origin with the transformed target, built once per target."""

    spec: TargetSpec
    table: pd.DataFrame
    x: np.ndarray
    offset_log: np.ndarray
    y_log: np.ndarray
    features: list[str]

    @property
    def z(self) -> np.ndarray:
        return np.asarray(self.y_log - self.offset_log, dtype=float)


def reference_offset(table: pd.DataFrame, reference: Reference) -> pd.Series:
    """Log reference subtracted from log(y): the 7-day mean, the seasonal naive or the last day."""
    if reference == "level7":
        return table["ref_log"]
    if reference == "seasonal_naive":
        return table["sn_log"]
    return table["last_log"]


def prepare(history: pd.DataFrame, spec: TargetSpec, config: ModelConfig) -> Prepared:
    table = feature_table(history, spec.name, spec.horizons)
    names = feature_names(spec.name)
    offset = reference_offset(table, config.reference)
    return Prepared(
        spec=spec,
        table=table,
        x=table[names].to_numpy(dtype=np.float32),
        offset_log=offset.to_numpy(dtype=float),
        y_log=attach_target(table, history, spec.name).to_numpy(dtype=float),
        features=names,
    )


def select_origins(
    last_day: pd.Timestamp, max_horizon: int, n: int, step: int
) -> list[pd.Timestamp]:
    """n origins `step` days apart, the last one leaving `max_horizon` observed days after it."""
    last = pd.Timestamp(last_day).as_unit("ns") - pd.Timedelta(days=max_horizon)
    return [last - pd.Timedelta(days=step * i) for i in reversed(range(n))]


def training_mask(prepared: Prepared, cutoff: pd.Timestamp) -> np.ndarray:
    """Rows usable at `cutoff`: target observed on or before it, transform defined."""
    day = prepared.table["day"].to_numpy()
    return (
        (day <= np.datetime64(pd.Timestamp(cutoff).as_unit("ns")))
        & ~np.isnan(prepared.y_log)
        & ~np.isnan(prepared.offset_log)
    )


def fit_at(prepared: Prepared, cutoff: pd.Timestamp, config: ModelConfig) -> list[Any]:
    mask = training_mask(prepared, cutoff)
    return fit_quantiles(prepared.x[mask], prepared.z[mask], config.params, prepared.features)


def predict_at(prepared: Prepared, boosters: list[Any], origin: pd.Timestamp) -> pd.DataFrame:
    """Raw quantile forecasts (log units) for one origin."""
    rows = np.flatnonzero(prepared.table["origin"].to_numpy() == np.datetime64(origin))
    if len(rows) == 0 or np.isnan(prepared.offset_log[rows]).any():
        raise ValueError(f"cannot forecast from {pd.Timestamp(origin).date()}")
    q = predict_quantiles(boosters, prepared.x[rows]) + prepared.offset_log[rows, None]
    return pd.DataFrame(
        {
            "h": prepared.table["h"].to_numpy()[rows],
            "day": prepared.table["day"].to_numpy()[rows],
            "q10_log": q[:, 0],
            "q50_log": q[:, 1],
            "q90_log": q[:, 2],
            "row": rows,
        }
    )


def backtest_target(
    history: pd.DataFrame,
    prepared: Prepared,
    origins: list[pd.Timestamp],
    n_warmup: int,
    config: ModelConfig,
    cfg: BacktestConfig,
) -> pd.DataFrame:
    """One row per (origin, h) with the actual, the model and the baselines."""
    spec = prepared.spec
    series = complete_daily(history)[spec.name]
    frames = []
    for i, origin in enumerate(origins):
        start = time.perf_counter()
        boosters = fit_at(prepared, origin, config)
        pred = predict_at(prepared, boosters, origin)
        sn = seasonal_naive_quantiles(series, origin, spec.horizon, cfg.sn_error_window_days)
        ets = ets_forecast(
            series, origin, spec.horizon, spec.name in cfg.log_targets, cfg.ets_window_days
        )
        pred["target"] = spec.name
        pred["origin"] = origin
        pred["warmup"] = i < n_warmup
        pred["bucket"] = [spec.bucket(int(h)) for h in pred["h"]]
        pred["y"] = series.reindex(pd.DatetimeIndex(pred["day"])).to_numpy()
        pred["scale"] = metrics.mase_scale(series.loc[:origin])
        for j, name in enumerate(("10", "50", "90")):
            pred[f"r{name}"] = np.exp(pred[f"q{name}_log"])
            pred[f"sn{name}"] = sn[:, j]
            pred[f"ets{name}"] = ets[:, j]
        frames.append(pred)
        log.info(
            "backtest_origin",
            target=spec.name,
            origin=str(origin.date()),
            warmup=i < n_warmup,
            seconds=round(time.perf_counter() - start, 1),
        )
    rows = pd.concat(frames, ignore_index=True)
    return calibrate_online(rows, cfg.min_calibration_origins, spec)


def bucket_offsets(rows: pd.DataFrame, spec: TargetSpec) -> dict[str, Offset]:
    """CQR offsets per horizon bucket from scored rows (bounds and actuals in log units)."""
    out: dict[str, Offset] = {}
    for lo, hi in spec.buckets:
        label = f"{lo}-{hi}"
        part = rows[rows["bucket"] == label]
        out[label] = conformal_offset(part["q10_log"], part["q90_log"], np.log(part["y"]))
    return out


def calibrate_online(rows: pd.DataFrame, min_origins: int, spec: TargetSpec) -> pd.DataFrame:
    """Add calibrated columns m10/m50/m90 using only outcomes observed before each origin."""
    rows = rows.copy()
    for name in ("m10", "m50", "m90"):
        rows[name] = np.nan
    rows["calibrated"] = False
    for origin in sorted(rows["origin"].unique()):
        here = rows["origin"] == origin
        past = rows[(rows["origin"] < origin) & (rows["day"] <= origin) & rows["y"].notna()]
        enough = past["origin"].nunique() >= min_origins
        offsets = bucket_offsets(past, spec) if enough else {}
        for label in rows.loc[here, "bucket"].unique():
            sel = here & (rows["bucket"] == label)
            q = rows.loc[sel, ["q10_log", "q50_log", "q90_log"]].to_numpy()
            adjusted = apply_offset(q, offsets.get(label, Offset()))
            rows.loc[sel, ["m10", "m50", "m90"]] = np.exp(adjusted)
        rows.loc[here, "calibrated"] = enough
    return rows


def _method_metrics(part: pd.DataFrame, prefix: str) -> dict[str, float]:
    y = part["y"].to_numpy()
    lo, mid, hi = (part[f"{prefix}{q}"].to_numpy() for q in ("10", "50", "90"))
    p10, p50, p90 = (
        metrics.pinball(y, q, a) for q, a in zip((lo, mid, hi), QUANTILES, strict=True)
    )
    return {
        "mape": metrics.mape(y, mid),
        "smape": metrics.smape(y, mid),
        "mase": metrics.mase(y, mid, part["scale"].to_numpy()),
        "pinball_p10": p10,
        "pinball_p50": p50,
        "pinball_p90": p90,
        "pinball_mean": (p10 + p50 + p90) / 3,
        "coverage_p10_p90": metrics.coverage(y, lo, hi),
        "below_p10": float(np.mean(y < lo)),
        "above_p90": float(np.mean(y > hi)),
        "width_rel": float(np.mean((hi - lo) / y)),
    }


def _all_methods(part: pd.DataFrame) -> dict[str, dict[str, float]]:
    return {m: _method_metrics(part, _COLS[m]) for m in METHODS}


def _paired(per_origin: pd.DataFrame, baseline: str) -> dict[str, Any]:
    model = per_origin["model"].to_numpy()
    base = per_origin[baseline].to_numpy()
    try:
        p_value: float | None = float(wilcoxon(model, base).pvalue)
    except ValueError:
        p_value = None
    return {
        "mase_model": float(model.mean()),
        "mase_baseline": float(base.mean()),
        "mase_reduction_pct": float((1 - model.mean() / base.mean()) * 100),
        "origins_won": int((model < base).sum()),
        "origins": len(model),
        "wilcoxon_p": p_value,
    }


def summarise(rows: pd.DataFrame, spec: TargetSpec) -> dict[str, Any]:
    """Metrics for reported (non warm-up) rows: overall, per bucket, per horizon, per origin."""
    rep = rows[~rows["warmup"]].dropna(subset=["y"])
    per_origin_records = []
    mase_rows = []
    for origin, part in rep.groupby("origin", sort=True):
        origin_day = pd.Timestamp(str(origin)).date()
        scores = {m: _method_metrics(part, _COLS[m]) for m in METHODS}
        mase_rows.append({m: scores[m]["mase"] for m in METHODS})
        per_origin_records.append(
            {
                "origin": str(origin_day),
                **{f"{m}_mase": round(scores[m]["mase"], 4) for m in METHODS if m != "model_raw"},
                "model_coverage": round(scores["model"]["coverage_p10_p90"], 4),
                "model_raw_coverage": round(scores["model_raw"]["coverage_p10_p90"], 4),
            }
        )
    per_origin = pd.DataFrame(mase_rows)
    by_horizon = {
        str(h): {
            m: {
                "mase": round(_method_metrics(part, _COLS[m])["mase"], 4),
                "coverage_p10_p90": round(_method_metrics(part, _COLS[m])["coverage_p10_p90"], 4),
            }
            for m in METHODS
        }
        for h, part in rep.groupby("h", sort=True)
    }
    return {
        "horizon": spec.horizon,
        "n_origins": int(rep["origin"].nunique()),
        "n_rows": len(rep),
        "first_origin": str(pd.Timestamp(rep["origin"].min()).date()),
        "last_origin": str(pd.Timestamp(rep["origin"].max()).date()),
        "nominal_coverage": 0.8,
        "overall": _all_methods(rep),
        "by_bucket": {
            label: _all_methods(rep[rep["bucket"] == label]) for label in rep["bucket"].unique()
        },
        "by_horizon": by_horizon,
        "by_origin": per_origin_records,
        "paired": {b: _paired(per_origin, b) for b in ("seasonal_naive", "ets")},
        "coverage": {
            "raw": _method_metrics(rep, "r")["coverage_p10_p90"],
            "calibrated": _method_metrics(rep[rep["calibrated"]], "m")["coverage_p10_p90"]
            if rep["calibrated"].any()
            else None,
            "uncalibrated_origins": int(rep.loc[~rep["calibrated"], "origin"].nunique()),
        },
    }


def rounded(value: Any, digits: int = 4) -> Any:
    """Round floats in a nested structure, for compact JSON."""
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, dict):
        return {k: rounded(v, digits) for k, v in value.items()}
    if isinstance(value, list):
        return [rounded(v, digits) for v in value]
    return value
