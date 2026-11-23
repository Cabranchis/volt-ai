"""The exchange rate and the oil price as price features.

Hypothesis: the price of the thermal plants that set the bolsa price when water is scarce follows the
cost of imported fuel, so the exchange rate (TRM) and Brent could say something about the price a week
or two ahead that the hydrology and the dispatch cost do not. Wholesale gas, the fuel that matters
most, has no daily machine-readable source (checked 2026-11-22), and XM publishes no maintenance
schedule or forecast metric, so these two are the only fuel and currency series that can be tested.

Two experiments (run_price.py machinery, the production LightGBM, the 37 scored development origins),
each the production features `dispatch+contracts+hydro` plus one block:
  fb_fx   TRM, last week against its 90-day mean and its 7-day change (known one day after its date)
  fb_oil  Brent, the same two features (known six days after its date)
The two blocks are not combined: one comparison per block. Nothing after the first reported origin is
used, and the blocks pass the same publication-lag leakage test as the others (test_features_ext.py).

Decision rule, written before the first run. A block is a candidate for production only if, against
`dispatch+contracts+hydro` on the same rows:
  1. the paired per-origin MASE difference (new minus reference) has a 95 % bootstrap interval whose
     upper end is below 0, and
  2. in none of the buckets (1-3, 4-7, 8-14 days) is the new model worse with an interval entirely
     above 0.
Pinball and the coverage of the calibrated range are reported, not used to decide. If a block fails,
the result is recorded as one more candidate and production does not change. If one passes, it would
run once on the reported origins (the harness refuses a second run) and ship only if it also improves
there, with an ADR; this script does not run the reported origins.

    uv run python research/fetch_fx_oil.py     # once, writes data/blocks_fx_oil.csv
    uv run python run_fx_oil.py                # from pipeline/research

Writes results/fx_oil.json (the comparison). Each experiment also writes
results/price_mean_cop_kwh/fb_fx.json and fb_oil.json.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

import harness
import run_price

REFERENCE = "dispatch+contracts+hydro"
EXPERIMENTS = {"fb_fx": "fx", "fb_oil": "oil"}
BUCKETS = ("1-3", "4-7", "8-14")


def compare(name: str, block: str, data: pd.DataFrame, origins: list[pd.Timestamp], base: object) -> dict[str, object]:
    experiment = run_price.GBMExperiment(blocks=(*run_price.FS1, block))
    result = run_price.run_gbm(name, experiment, data, origins, base)
    print(run_price.summary_line(name, result), flush=True)
    new = pd.read_csv(harness.DATA / f"rows_{name}.csv", parse_dates=["origin", "day"])
    old = pd.read_csv(harness.DATA / f"rows_{REFERENCE}.csv", parse_dates=["origin", "day"])
    merged = new.merge(
        old[["origin", "h", "m10", "m50", "m90"]], on=["origin", "h"], suffixes=("", "_ref"), validate="one_to_one"
    )
    for q in ("10", "50", "90"):
        merged[f"o{q}"] = merged[f"m{q}_ref"]
    paired_mase = harness.paired(merged, "m", "o", "mase")
    by_bucket = {b: harness.paired(merged[merged["bucket"] == b], "m", "o", "mase") for b in BUCKETS}
    reference = json.loads((harness.RESULTS / "price_mean_cop_kwh" / f"{REFERENCE}.json").read_text())
    worse = [b for b, p in by_bucket.items() if p["ci_low"] > 0]
    checks = {
        "mase_interval_below_zero": bool(paired_mase["ci_high"] < 0),
        "no_bucket_clearly_worse": not worse,
    }
    return {
        "experiment": name,
        "block": block,
        "reference": REFERENCE,
        "origins": int(merged.loc[~merged["warmup"].astype(bool), "origin"].nunique()),  # scored, not warm-up
        "model": {k: result["model"][k] for k in ("mase", "mape", "pinball_mean", "coverage")},
        "reference_model": {k: reference["model"][k] for k in ("mase", "mape", "pinball_mean", "coverage")},
        "paired_mase_new_minus_reference": paired_mase,
        "paired_mase_by_bucket": by_bucket,
        "buckets_clearly_worse": worse,
        "checks": checks,
        "candidate_for_production": all(checks.values()),
    }


def main() -> None:
    data = harness.load_data()
    assert {"trm", "brent"} <= set(data.columns), "run research/fetch_fx_oil.py first"
    target = run_price.TARGET
    origins = harness.dev_origins(target)
    harness.assert_development(origins, target)
    base = harness.cached_baselines(data, target, origins, "dev")
    out = {name: compare(name, block, data, origins, base) for name, block in EXPERIMENTS.items()}
    harness.RESULTS.joinpath("fx_oil.json").write_text(json.dumps(harness.rounded(out), indent=2), encoding="utf-8")
    print(json.dumps(harness.rounded(out), indent=2))
    assert all(np.isfinite(v["paired_mase_new_minus_reference"]["mean_diff"]) for v in out.values())  # type: ignore[index]


if __name__ == "__main__":
    main()
