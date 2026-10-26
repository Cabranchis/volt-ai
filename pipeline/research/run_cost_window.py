"""How well does a 'cost of a window' range hold? Measures the coverage of the P10-P90 range of the
mean spot price over a window of days, built from the production price forecast's daily bands.

The daily bands cannot be added up: the P10 of a window equals the sum of the daily P10 only when
the days move together perfectly. This script runs the production price backtest (same fixed
calendar of origins as docs/model-card.md), then, for several correlations rho between days and
for windows of 3, 7 and 12 days, simulates the window mean from the daily bands and counts how
often the real mean falls inside. It decides the rho the web calculator uses.

Windows start at horizon 3: the forecast is issued about three days after the last complete day,
so horizon 3 is the day it is issued, which is the first day the web calculator counts. The price
horizon is 14, so the longest window is 12 days.

Usage (local SQLite, never the production URL):
    DATABASE_URL=sqlite:///D:/Projects/voltia/pipeline/data/voltia.sqlite python run_cost_window.py
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

import harness
from voltia import db
from voltia.config import get_settings
from voltia.features import TARGETS, complete_daily
from voltia.forecast import REFERENCES, last_settled_day, observed_origin
from voltia.models.backtest import (
    BacktestConfig,
    ModelConfig,
    anchored_origins,
    backtest_target,
    block_bootstrap_ci,
    prepare,
)
from voltia.models.gbm import GBMParams

TARGET = "price_mean_cop_kwh"
START = 3
LENGTHS = (3, 7, 12)
RHOS = (0.0, 0.3, 0.5, 0.7, 0.9, 1.0)
Z90 = 1.2815515655446004
DRAWS = 4000


def window_range(day_rows: pd.DataFrame, rho: float, rng: np.random.Generator) -> tuple[float, float, float]:
    """P10, P50 and P90 of the window mean price, from the daily calibrated bands."""
    mu = np.log(day_rows["m50"].to_numpy())
    sigma = np.maximum((np.log(day_rows["m90"].to_numpy()) - np.log(day_rows["m10"].to_numpy())) / (2 * Z90), 1e-3)
    common = rng.standard_normal((DRAWS, 1))
    own = rng.standard_normal((DRAWS, len(mu)))
    z = np.sqrt(rho) * common + np.sqrt(1 - rho) * own
    mean = np.exp(mu + sigma * z).mean(axis=1)
    p10, p50, p90 = np.percentile(mean, [10, 50, 90])
    return float(p10), float(p50), float(p90)


def main() -> None:
    settings = get_settings()
    engine = db.make_engine(settings.resolved_database_url)
    if engine.dialect.name != "sqlite":
        raise SystemExit("run this against the local SQLite file, not the production database")
    hist = complete_daily(db.read_series(engine))
    spec = TARGETS[TARGET]
    cfg = BacktestConfig()
    end = last_settled_day(hist, [TARGET])
    planned = anchored_origins(pd.Timestamp(cfg.anchor), end, spec.horizon, cfg.step_days, cfg.n_warmup)
    origins = [observed_origin(hist, [TARGET], o) for o in planned]
    config = ModelConfig(reference=REFERENCES[TARGET], params=GBMParams())
    prepared = prepare(hist, spec, config)
    rows = backtest_target(hist, prepared, origins, cfg.n_warmup, config, cfg)
    rows = rows[(~rows["warmup"]) & rows["calibrated"] & rows["y"].notna()]

    results: dict[str, dict[str, object]] = {}
    rng = np.random.default_rng(11)
    for length in LENGTHS:
        window = range(START, START + length)
        for rho in RHOS:
            inside, widths, below = [], [], []
            for _, part in rows.groupby("origin"):
                part = part[part["h"].isin(window)].sort_values("h")
                if len(part) != length:
                    continue
                p10, p50, p90 = window_range(part, rho, rng)
                actual = float(part["y"].mean())
                inside.append(float(p10 <= actual <= p90))
                below.append(float(actual < p10))
                widths.append((p90 - p10) / p50)
            arr = np.array(inside)
            block = max(3, int(np.ceil((START + length) / cfg.step_days)))
            lo, hi = block_bootstrap_ci(arr, block)
            results[f"{length}d/rho={rho}"] = {
                "length": length,
                "rho": rho,
                "origins": int(len(arr)),
                "coverage": round(float(arr.mean()), 3),
                "coverage_ci95": [round(lo, 3), round(hi, 3)],
                "share_below_p10": round(float(np.mean(below)), 3),
                "share_above_p90": max(0.0, round(1 - float(arr.mean()) - float(np.mean(below)), 3)),
                "mean_relative_width": round(float(np.mean(widths)), 3),
            }
            print(f"{length:>2} days rho={rho:<4} coverage={arr.mean():.2f} width={np.mean(widths):.2f} n={len(arr)}")

    out = harness.RESULTS / f"cost_window_{date.today().isoformat()}.json"
    out.write_text(json.dumps({"data_end": str(end.date()), "start_horizon": START, "results": results}, indent=2))
    print("saved", out)


if __name__ == "__main__":
    main()
