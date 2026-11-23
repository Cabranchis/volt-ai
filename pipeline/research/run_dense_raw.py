"""The dense backtest again, keeping the raw quantiles that the adaptive calibration needs.

`run_dense_backtest.py` keeps only the calibrated band (m10, m50, m90), so a new calibration cannot be
tried on it: that needs the quantiles before calibration (q10_log, q50_log, q90_log, absolute logs of
the price or the demand) plus the raw band r10..r90 in the units of the target. This runs
the same production model and calibration (`backtest_target`) on origins every 7 days and saves the
columns of every row. Price and demand.

    DATABASE_URL=sqlite:///data/voltia.sqlite uv run python research/run_dense_raw.py price|demand

Writes research/results/dense_raw_<target>.json, one row per origin and horizon. Local SQLite only:
the script refuses to run against another database. For the price it checks that the calibrated
centre `m50` equals the one saved by `run_dense_backtest.py` (the run is deterministic), so the two
files describe the same backtest.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from run_dense_backtest import add_persistence
from voltia import db
from voltia.features import TARGETS, complete_daily
from voltia.forecast import REFERENCES, last_settled_day, observed_origin
from voltia.models.backtest import (
    BacktestConfig,
    ModelConfig,
    anchored_origins,
    backtest_target,
    prepare,
)
from voltia.models.gbm import GBMParams

NAMES = {"price": "price_mean_cop_kwh", "demand": "demand_kwh"}
HERE = Path(__file__).parent
STEP = 7
WARMUP = 24  # 24 x 7 days = the same 168 days of warm-up as the production backtest
KEEP = [
    "origin", "day", "h", "bucket", "warmup", "y", "scale",
    "q10_log", "q50_log", "q90_log", "r10", "r50", "r90", "m10", "m50", "m90", "calibrated",
]  # fmt: skip


def run(name: str) -> pd.DataFrame:
    if db.make_engine().dialect.name != "sqlite":
        sys.exit("refusing to run against a non-SQLite database (set DATABASE_URL)")
    hist = complete_daily(db.read_series(db.make_engine()))
    spec = TARGETS[name]
    cfg = BacktestConfig(step_days=STEP, n_warmup=WARMUP)
    end = last_settled_day(hist, [name])
    planned = anchored_origins(pd.Timestamp(cfg.anchor), end, spec.horizon, STEP, WARMUP)
    origins = [observed_origin(hist, [name], o) for o in planned]
    config = ModelConfig(reference=REFERENCES[name], params=GBMParams())
    prepared = prepare(hist, spec, config)
    rows = backtest_target(hist, prepared, origins, WARMUP, config, cfg)
    # The warm-up origins stay (flag `warmup`): production calibrates on them too, so a calibration
    # that must reproduce it needs their outcomes.
    rows = rows[rows["y"].notna()].copy()
    if name == "price_mean_cop_kwh":
        rows = add_persistence(rows, hist[name])
    return rows


def check_against_saved(rows: pd.DataFrame) -> None:
    saved = pd.DataFrame(json.loads((HERE / "results" / "dense_backtest.json").read_text()))
    mine = rows[~rows["warmup"]].assign(
        origin=rows["origin"].dt.strftime("%Y-%m-%d"), day=rows["day"].dt.strftime("%Y-%m-%d")
    )
    merged = saved.merge(mine, on=["origin", "day", "h"], suffixes=("_saved", ""))
    assert len(merged) == len(saved), "the origins differ from the saved dense backtest"
    worst = float((merged["m50_saved"] - merged["m50"]).abs().max())
    assert worst < 1e-2, f"m50 differs from the saved file by {worst}"
    print(f"matches the saved dense backtest: {len(merged)} rows, largest difference {worst:.5f}")


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "price"
    name = NAMES[which]
    out = HERE / "results" / f"dense_raw_{which}.json"
    rows = run(name)
    if which == "price":
        check_against_saved(rows)
    stored = rows[KEEP].copy()
    stored["origin"] = pd.to_datetime(stored["origin"]).dt.strftime("%Y-%m-%d")
    stored["day"] = pd.to_datetime(stored["day"]).dt.strftime("%Y-%m-%d")
    stored["calibrated"] = stored["calibrated"].astype(bool)
    stored["warmup"] = stored["warmup"].astype(bool)
    assert np.isfinite(stored[["q10_log", "q50_log", "q90_log", "m10", "m50", "m90"]].to_numpy()).all()
    out.write_text(json.dumps(stored.round(6).to_dict("records"), separators=(",", ":")))
    print("wrote", out, stored["origin"].nunique(), "origins", len(stored), "rows")


if __name__ == "__main__":
    main()
