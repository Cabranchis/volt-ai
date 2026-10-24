"""Training runs, the on-disk model store and production forecasts (FR-06 to FR-08).

A run backtests every target, fits the final boosters on all settled data, and derives the
interval calibration from the backtest's out-of-sample scores. Boosters are stored as
LightGBM text files with a JSON manifest (no pickle), so `voltia predict` needs no retraining.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

import lightgbm as lgb
import numpy as np
import pandas as pd
import structlog

from voltia.db import utcnow
from voltia.explain import shap_values, top_drivers
from voltia.features import (
    ONI_PUBLICATION_LAG_DAYS,
    TARGETS,
    TargetSpec,
    build_features,
    complete_daily,
)
from voltia.models.backtest import (
    BacktestConfig,
    ModelConfig,
    Reference,
    backtest_target,
    bucket_offsets,
    fit_at,
    prepare,
    reference_offset,
    rounded,
    select_origins,
    summarise,
)
from voltia.models.calibration import Offset, apply_offset
from voltia.models.gbm import QUANTILES, GBMParams, predict_quantiles

log = structlog.get_logger()

# Chosen on development origins from 2021-07 to 2023-01, before any reported origin.
REFERENCES: dict[str, Reference] = {"demand_kwh": "last", "price_mean_cop_kwh": "last"}
STORE_RUNS_KEPT = 3


@dataclass
class TrainedTarget:
    spec: TargetSpec
    reference: Reference
    features: list[str]
    boosters: list[lgb.Booster]
    offsets: dict[str, Offset]


@dataclass
class TrainResult:
    run_id: str
    trained_at: datetime
    data_start: date
    data_end: date
    metrics: dict[str, Any]
    params: dict[str, Any]
    models: dict[str, TrainedTarget]
    seconds: float


def last_settled_day(history: pd.DataFrame, targets: list[str]) -> pd.Timestamp:
    """Newest day on which every target has a value (XM settles demand and price last)."""
    days = []
    for name in targets:
        last = history[name].last_valid_index()
        if last is None:
            raise ValueError(f"no data for {name}")
        days.append(pd.Timestamp(str(last)))
    return min(days).as_unit("ns")


def observed_origin(
    history: pd.DataFrame, targets: list[str], origin: pd.Timestamp
) -> pd.Timestamp:
    """The origin, or the closest earlier day (up to 7) on which every target was observed."""
    for back in range(8):
        day = origin - pd.Timedelta(days=back)
        if day in history.index and history.loc[day, targets].notna().all():
            if back:
                log.warning("origin_moved", planned=str(origin.date()), used=str(day.date()))
            return day
    raise ValueError(f"no observed targets in the week before {origin.date()}")


def make_run_id(trained_at: datetime, history: pd.DataFrame, params: dict[str, Any]) -> str:
    fingerprint = int(pd.util.hash_pandas_object(history, index=True).sum())
    payload = f"{fingerprint}|{json.dumps(params, sort_keys=True, default=str)}"
    digest = hashlib.sha256(payload.encode()).hexdigest()[:7]
    return f"{trained_at:%Y%m%dT%H%M%SZ}-{digest}"


def train(
    history: pd.DataFrame,
    params: GBMParams | None = None,
    cfg: BacktestConfig | None = None,
    targets: dict[str, TargetSpec] | None = None,
    trained_at: datetime | None = None,
) -> TrainResult:
    """Backtest, calibrate and fit the final models for every target."""
    params = params or GBMParams()
    cfg = cfg or BacktestConfig()
    targets = targets or TARGETS
    start = time.perf_counter()
    end = last_settled_day(history, list(targets))
    hist = complete_daily(history).loc[:end]
    max_horizon = max(spec.horizon for spec in targets.values())
    planned = select_origins(end, max_horizon, cfg.n_warmup + cfg.n_origins, cfg.step_days)
    origins = [observed_origin(hist, list(targets), o) for o in planned]

    target_metrics: dict[str, Any] = {}
    models: dict[str, TrainedTarget] = {}
    for name, spec in targets.items():
        config = ModelConfig(reference=REFERENCES[name], params=params)
        prepared = prepare(hist, spec, config)
        rows = backtest_target(hist, prepared, origins, cfg.n_warmup, config, cfg)
        target_metrics[name] = rounded(summarise(rows, spec))
        offsets = bucket_offsets(rows[rows["y"].notna()], spec)
        target_metrics[name]["calibration_offsets"] = {
            label: rounded(asdict(off)) for label, off in offsets.items()
        }
        models[name] = TrainedTarget(
            spec=spec,
            reference=config.reference,
            features=prepared.features,
            boosters=fit_at(prepared, end, config),
            offsets=offsets,
        )
        log.info("target_trained", target=name, seconds=round(time.perf_counter() - start, 1))

    run_params = {
        "gbm": asdict(params),
        "quantiles": list(QUANTILES),
        "references": {name: REFERENCES[name] for name in targets},
        "horizons": {name: spec.horizon for name, spec in targets.items()},
        "features": {name: m.features for name, m in models.items()},
        "oni_publication_lag_days": ONI_PUBLICATION_LAG_DAYS,
        "calibration": "asymmetric CQR per horizon bucket, past out-of-sample scores only",
        "versions": {pkg: version(pkg) for pkg in ("lightgbm", "statsmodels", "shap", "pandas")},
    }
    trained_at = trained_at or utcnow()
    seconds = time.perf_counter() - start
    metrics = {
        "backtest": {
            **cfg.to_dict(),
            "origins": [str(o.date()) for o in origins[cfg.n_warmup :]],
            "warmup_origins": [str(o.date()) for o in origins[: cfg.n_warmup]],
            "train_seconds": round(seconds, 1),
        },
        "targets": target_metrics,
    }
    return TrainResult(
        run_id=make_run_id(trained_at, hist, run_params),
        trained_at=trained_at,
        data_start=hist.index[0].date(),
        data_end=end.date(),
        metrics=metrics,
        params=run_params,
        models=models,
        seconds=seconds,
    )


def forecast_target(
    history: pd.DataFrame, model: TrainedTarget, origin: pd.Timestamp | None = None
) -> pd.DataFrame:
    """Calibrated P10/P50/P90 for the days after `origin` (default: last day of the target)."""
    spec = model.spec
    if origin is None:
        last = history[spec.name].last_valid_index()
        if last is None:
            raise ValueError(f"no data for {spec.name}")
        origin = pd.Timestamp(str(last))
    feats = build_features(history, origin, spec.horizons, spec.name)
    x = feats[model.features].to_numpy(dtype=np.float32)
    offset = reference_offset(feats, model.reference).to_numpy(dtype=float)
    if np.isnan(offset).any():
        raise ValueError(f"reference level undefined at {pd.Timestamp(origin).date()}")
    q = predict_quantiles(model.boosters, x) + offset[:, None]
    p50 = np.exp(q[:, 1])  # calibration moves only the outer quantiles
    buckets = np.array([spec.bucket(int(h)) for h in feats["h"]])
    for label in np.unique(buckets):
        sel = buckets == label
        q[sel] = apply_offset(q[sel], model.offsets.get(str(label), Offset()))
    # SHAP explains the median booster; contributions are scaled to the stored P50.
    median_booster = model.boosters[QUANTILES.index(0.5)]
    drivers = top_drivers(shap_values(median_booster, x), p50, model.features)
    values = np.exp(q)
    return pd.DataFrame(
        {
            "target": spec.name,
            "day": pd.DatetimeIndex(feats["day"]),
            "horizon": feats["h"].to_numpy(dtype=int),
            "p10": values[:, 0],
            "p50": values[:, 1],
            "p90": values[:, 2],
            "drivers": drivers,
        }
    )


def save_models(directory: Path, result: TrainResult, keep: int = STORE_RUNS_KEPT) -> Path:
    """Write boosters and a manifest under directory/run_id and point latest.json at it."""
    run_dir = directory / result.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "run_id": result.run_id,
        "data_end": str(result.data_end),
        "targets": {},
    }
    for name, model in result.models.items():
        files = []
        for q, booster in zip(QUANTILES, model.boosters, strict=True):
            path = run_dir / f"{name}_p{round(q * 100):02d}.txt"
            booster.save_model(str(path))
            files.append(path.name)
        manifest["targets"][name] = {
            "horizon": model.spec.horizon,
            "buckets": [list(b) for b in model.spec.buckets],
            "reference": model.reference,
            "features": model.features,
            "files": files,
            "offsets": {label: asdict(off) for label, off in model.offsets.items()},
        }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (directory / "latest.json").write_text(json.dumps({"run_id": result.run_id}), encoding="utf-8")
    runs = sorted((p for p in directory.iterdir() if p.is_dir()), key=lambda p: p.name)
    for old in runs[:-keep]:
        shutil.rmtree(old)
    return run_dir


def load_models(directory: Path) -> tuple[str, dict[str, TrainedTarget]]:
    """Load the latest stored run. Raises FileNotFoundError if nothing was trained yet."""
    latest = directory / "latest.json"
    if not latest.exists():
        raise FileNotFoundError(f"no trained models in {directory}; run `voltia train` first")
    run_id = str(json.loads(latest.read_text(encoding="utf-8"))["run_id"])
    manifest = json.loads((directory / run_id / "manifest.json").read_text(encoding="utf-8"))
    models: dict[str, TrainedTarget] = {}
    for name, entry in manifest["targets"].items():
        buckets = tuple((int(lo), int(hi)) for lo, hi in entry["buckets"])
        spec = TargetSpec(name, int(entry["horizon"]), buckets)
        models[name] = TrainedTarget(
            spec=spec,
            reference=cast(Reference, entry["reference"]),
            features=list(entry["features"]),
            boosters=[lgb.Booster(model_file=str(directory / run_id / f)) for f in entry["files"]],
            offsets={label: Offset(**off) for label, off in entry["offsets"].items()},
        )
    return run_id, models
