"""Average the raw log-quantile forecasts of several finished experiments and re-score them.

Usage: python ensemble.py <name> <member> <member> ... (members are experiment names whose
data/rows_<member>.csv exist). The ensemble is recalibrated online like any single model.
"""

from __future__ import annotations

import sys

import pandas as pd

import harness
import run_price
from voltia.features import TARGETS

TARGET = TARGETS["price_mean_cop_kwh"]


def combine(members: list[str], weights: list[float] | None = None) -> pd.DataFrame:
    frames = [pd.read_csv(harness.DATA / f"rows_{m}.csv", parse_dates=["origin", "day"]) for m in members]
    keys = ["origin", "h", "day"]
    w = weights or [1 / len(frames)] * len(frames)
    base = frames[0][keys].copy()
    for q in ("q10_log", "q50_log", "q90_log"):
        base[q] = sum(wi * f[q] for wi, f in zip(w, frames, strict=True))
    return base


def run(name: str, members: list[str], weights: list[float] | None = None) -> dict:
    data = harness.load_data()
    origins = harness.dev_origins(TARGET)
    harness.assert_development(origins, TARGET)
    base = harness.cached_baselines(data, TARGET, origins, "dev")
    pred = combine(members, weights)
    rows = harness.finish_rows(pred, data, TARGET, base)
    rows.to_csv(harness.DATA / f"rows_{name}.csv", index=False)
    result = harness.score(rows)
    result["experiment"] = {"name": name, "ensemble_of": members, "weights": weights}
    result["paired_vs_ets_mase"] = harness.paired(rows, "m", "ets", "mase")
    result["paired_vs_ets_pinball"] = harness.paired(rows, "m", "ets", "pinball")
    result["seconds"] = 0.0
    harness.save_result(name, TARGET.name, result)
    return result


if __name__ == "__main__":
    name, *members = sys.argv[1:]
    print(run_price.summary_line(name, run(name, members)))
