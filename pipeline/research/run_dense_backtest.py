"""Price backtest with test dates every 7 days and the "repeat the last price" reference.

The production backtest has 51 test dates 21 days apart, only 4 to 12 of them in each episode, and
compares the model with ETS and a weekly seasonal naive. The live record compares it with the last
settled price. This script runs the same production model and calibration on dates every 7 days (about
three times as many, more correlated) and adds that third reference, so the claims about stress and
calm periods rest on more dates and on the reference a client would use.

    DATABASE_URL=sqlite:///data/voltia.sqlite uv run python research/run_dense_backtest.py

Writes research/results/dense_backtest.json (one row per origin and horizon) and prints the tables.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

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

NAME = "price_mean_cop_kwh"
SETTLE_LAG = 3  # days between a price day and the day XM publishes its settled price
OUT = Path(__file__).parent / "results" / "dense_backtest.json"
STEP = 7
WARMUP = 24  # 24 x 7 days = the same 168 days of warm-up as the production backtest
PERIODS = {
    "El Niño 2023-24": ("2023-11-01", "2024-04-30"),
    "Supply shock 2024": ("2024-05-01", "2024-12-31"),
    "Calm 2025-26": ("2025-01-01", "2026-06-30"),
    "El Niño 2026": ("2026-07-01", "2026-12-31"),
    "All": ("2000-01-01", "2999-01-01"),
}
BUCKETS = {"1-3": (1, 3), "4-7": (4, 7), "8-14": (8, 14)}


def run() -> pd.DataFrame:
    if db.make_engine().dialect.name != "sqlite":
        sys.exit("refusing to run against a non-SQLite database (set DATABASE_URL)")
    hist = complete_daily(db.read_series(db.make_engine()))
    spec = TARGETS[NAME]
    cfg = BacktestConfig(step_days=STEP, n_warmup=WARMUP)
    end = last_settled_day(hist, [NAME])
    planned = anchored_origins(pd.Timestamp(cfg.anchor), end, spec.horizon, STEP, WARMUP)
    origins = [observed_origin(hist, [NAME], o) for o in planned]
    config = ModelConfig(reference=REFERENCES[NAME], params=GBMParams())
    prepared = prepare(hist, spec, config)
    rows = backtest_target(hist, prepared, origins, WARMUP, config, cfg)
    rows = rows[~rows["warmup"] & rows["y"].notna()].copy()
    price = hist[NAME]
    last_known = {
        o: float(price.loc[: o - pd.Timedelta(days=SETTLE_LAG)].dropna().iloc[-1])
        for o in rows["origin"].unique()
    }
    rows["persist"] = rows["origin"].map(last_known)
    return rows


def per_origin(rows: pd.DataFrame) -> pd.DataFrame:
    """MASE and MAPE of each method on each origin (and horizon bucket)."""
    out = []
    for (origin, bucket), part in rows.groupby(["origin", "bucket"]):
        y, scale = part["y"].to_numpy(), part["scale"].to_numpy()
        entry = {"origin": origin, "bucket": bucket}
        for name, col in (("model", "m50"), ("ets", "ets50"), ("naive", "sn50"), ("persist", "persist")):
            err = np.abs(part[col].to_numpy() - y)
            entry[f"mase_{name}"] = float(np.mean(err / scale))
            entry[f"mape_{name}"] = float(np.mean(err / y) * 100)
        entry["inside"] = float(np.mean((y >= part["m10"]) & (y <= part["m90"])))
        out.append(entry)
    return pd.DataFrame(out)


def block_ci(diff: np.ndarray, block: int = 6, n_boot: int = 4000, seed: int = 7) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(diff)
    starts = np.arange(0, max(n - block + 1, 1))
    reps = math.ceil(n / block)
    means = [
        np.concatenate([diff[s : s + block] for s in rng.choice(starts, reps)])[:n].mean()
        for _ in range(n_boot)
    ]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def report(rows: pd.DataFrame) -> dict[str, object]:
    po = per_origin(rows)
    po["origin"] = pd.to_datetime(po["origin"])
    summary: dict[str, object] = {}
    print("\nPrice, MAPE % by period and horizon (model | ETS | naive | repeat last price); origins every 7 days")
    for label, (lo, hi) in PERIODS.items():
        part = po[(po["origin"] >= lo) & (po["origin"] <= hi)]
        n = part["origin"].nunique()
        line = [f"{label} ({n} dates)"]
        entry: dict[str, object] = {"origins": int(n)}
        for bucket in BUCKETS:
            b = part[part["bucket"] == bucket]
            vals = [b[f"mape_{m}"].mean() for m in ("model", "ets", "naive", "persist")]
            line.append(f"{bucket}: " + " | ".join(f"{v:5.1f}" for v in vals))
            entry[bucket] = {m: round(float(v), 1) for m, v in zip(("model", "ets", "naive", "persist"), vals, strict=True)}
        print("  " + "  ".join(line))
        summary[label] = entry
    print("\nMASE overall, share of dates the model is better, paired difference vs each reference [95 % CI]")
    full = po.groupby("origin")[[c for c in po.columns if c.startswith("mase_")] + ["inside"]].mean().reset_index()
    for label, (lo, hi) in PERIODS.items():
        part = full[(full["origin"] >= lo) & (full["origin"] <= hi)].sort_values("origin")
        if part.empty:
            continue
        text = [f"{label} ({len(part)})", f"MASE model {part['mase_model'].mean():.2f}"]
        for ref in ("ets", "naive", "persist"):
            diff = (part["mase_model"] - part[f"mase_{ref}"]).to_numpy()
            ci = block_ci(diff)
            text.append(f"{ref} {part[f'mase_{ref}'].mean():.2f} (wins {np.mean(diff < 0):.0%}, diff {diff.mean():+.2f} [{ci[0]:+.2f},{ci[1]:+.2f}])")
        text.append(f"inside band {part['inside'].mean():.0%}")
        print("  " + "; ".join(text))
    return summary


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        rows = pd.DataFrame(json.loads(OUT.read_text()))
        rows["origin"] = pd.to_datetime(rows["origin"])
        rows["day"] = pd.to_datetime(rows["day"])
    else:
        rows = run()
        keep = ["origin", "day", "h", "bucket", "y", "scale", "m10", "m50", "m90", "ets50", "sn50", "persist"]
        out = rows[keep].copy()
        out["origin"] = out["origin"].dt.strftime("%Y-%m-%d")
        out["day"] = out["day"].dt.strftime("%Y-%m-%d")
        OUT.write_text(json.dumps(out.round(4).to_dict("records"), separators=(",", ":")))
        print("wrote", OUT, rows["origin"].nunique(), "origins")
    report(rows)


if __name__ == "__main__":
    main()
