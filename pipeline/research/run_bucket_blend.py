"""Blend a finished experiment with ETS, with a weight per horizon bucket learned online.

Usage: python run_bucket_blend.py <name> <member>

At every origin the weight of each bucket is the one (grid 0 to 1 in steps of 0.1) that minimised
the mean pinball loss of the blended log-quantiles on the rows of the earlier origins, whose
outcomes are all known because origins are further apart than the horizon. Before any history the
weight is 0.5. Nothing from the origin being forecast, or after it, is used.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import harness
import run_price
from voltia.features import TARGETS
from voltia.models import metrics

TARGET = TARGETS["price_mean_cop_kwh"]
GRID = np.round(np.arange(0.0, 1.01, 0.1), 1)
QS = (("10", 0.1), ("50", 0.5), ("90", 0.9))


def blended(rows: pd.DataFrame, weight: float) -> dict[str, np.ndarray]:
    return {q: weight * rows[f"q{q}_log"].to_numpy() + (1 - weight) * np.log(rows[f"ets{q}"].to_numpy()) for q, _ in QS}


def loss(rows: pd.DataFrame, weight: float) -> float:
    y = rows["y"].to_numpy()
    b = blended(rows, weight)
    return float(np.mean([metrics.pinball(y, np.exp(b[q]), a) for q, a in QS]))


def run(name: str, member: str) -> dict:
    data = harness.load_data()
    origins = harness.dev_origins(TARGET)
    harness.assert_development(origins, TARGET)
    base = harness.cached_baselines(data, TARGET, origins, "dev")
    rows = pd.read_csv(harness.DATA / f"rows_{member}.csv", parse_dates=["origin", "day"])
    rows = rows.dropna(subset=["y"]).copy()
    out = []
    weights: dict[tuple[pd.Timestamp, str], float] = {}
    for origin in sorted(rows["origin"].unique()):
        past = rows[rows["origin"] < origin]
        now = rows[rows["origin"] == origin]
        for bucket, part in now.groupby("bucket"):
            history = past[past["bucket"] == bucket]
            if len(history) < 30:
                w = 0.5
            else:
                w = float(GRID[int(np.argmin([loss(history, g) for g in GRID]))])
            weights[(origin, str(bucket))] = w
            b = blended(part, w)
            out.append(part[["origin", "h", "day"]].assign(q10_log=b["10"], q50_log=b["50"], q90_log=b["90"]))
    pred = pd.concat(out, ignore_index=True)
    scored = harness.finish_rows(pred, data, TARGET, base)
    scored.to_csv(harness.DATA / f"rows_{name}.csv", index=False)
    result = harness.score(scored)
    result["target"] = TARGET.name
    result["experiment"] = {"name": name, "blend_of": [member, "ets"], "online_bucket_weights": True}
    result["paired_vs_ets_mase"] = harness.paired(scored, "m", "ets", "mase")
    result["paired_vs_ets_pinball"] = harness.paired(scored, "m", "ets", "pinball")
    result["seconds"] = 0.0
    last = {b: w for (o, b), w in weights.items() if o == max(rows["origin"])}
    result["final_weights"] = last
    harness.save_result(name, TARGET.name, result)
    print("last weights per bucket (model share):", last)
    return result


if __name__ == "__main__":
    print(run_price.summary_line(sys.argv[1], run(sys.argv[1], sys.argv[2])))
