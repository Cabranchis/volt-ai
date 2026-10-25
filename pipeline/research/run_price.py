"""Price experiments on the development origins. Usage: python run_price.py <name> [<name> ...]

Each experiment is a LightGBM variant (features, reference, parameters). Results go to
results/price_mean_cop_kwh/<name>.json and the per-row forecasts to data/rows_<name>.csv.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

import features_ext
import harness
from voltia.features import TARGETS, feature_names
from voltia.models.backtest import ModelConfig, Prepared, fit_at, predict_at, prepare
from voltia.models.gbm import GBMParams

TARGET = TARGETS["price_mean_cop_kwh"]
PARAMS = GBMParams(num_threads=6)


@dataclass(frozen=True)
class GBMExperiment:
    blocks: tuple[str, ...] = ()
    reference: str = "last"
    params: GBMParams = PARAMS
    lag_overrides: dict[str, int] = field(default_factory=dict)
    drop: tuple[str, ...] = ()


EXPERIMENTS: dict[str, GBMExperiment] = {
    "current": GBMExperiment(),
    "dispatch": GBMExperiment(blocks=("dispatch",)),
    "dispatch_optimistic": GBMExperiment(blocks=("dispatch",), lag_overrides={"dispatch_cost": 0, "dispatch_cost_max": 0}),
    "offers": GBMExperiment(blocks=("offers",)),
    "contracts": GBMExperiment(blocks=("contracts",)),
    "hydro_now": GBMExperiment(blocks=("hydro_now",)),
    "trade": GBMExperiment(blocks=("trade",)),
    "dispatch+contracts": GBMExperiment(blocks=("dispatch", "contracts")),
    "dispatch+contracts+hydro": GBMExperiment(blocks=("dispatch", "contracts", "hydro_now")),
    "all_blocks": GBMExperiment(blocks=features_ext.BLOCKS),
}


def extended(data: pd.DataFrame, exp: GBMExperiment) -> Prepared:
    prepared = prepare(data, TARGET, ModelConfig(reference=exp.reference, params=exp.params))  # type: ignore[arg-type]
    if not exp.blocks:
        return prepared
    extra = features_ext.add_blocks(prepared.table, data, exp.blocks, exp.lag_overrides)
    names = [n for n in prepared.features if n not in exp.drop] + list(extra.columns)
    keep = [prepared.features.index(n) for n in prepared.features if n not in exp.drop]
    x = np.hstack([prepared.x[:, keep], extra.to_numpy(dtype=np.float32)])
    return replace(prepared, x=x, features=names)


def run_gbm(name: str, exp: GBMExperiment, data: pd.DataFrame, origins: list[pd.Timestamp], base: pd.DataFrame) -> dict:
    start = time.perf_counter()
    prepared = extended(data, exp)
    config = ModelConfig(reference=exp.reference, params=exp.params)  # type: ignore[arg-type]
    frames = []
    for origin in origins:
        boosters = fit_at(prepared, origin, config)
        pred = predict_at(prepared, boosters, origin)
        pred = pred.drop(columns=["row"])
        pred.insert(0, "origin", origin)
        frames.append(pred)
    rows = harness.finish_rows(pd.concat(frames, ignore_index=True), data, TARGET, base)
    rows.to_csv(harness.DATA / f"rows_{name}.csv", index=False)
    result = harness.score(rows)
    result["experiment"] = {"name": name, "blocks": list(exp.blocks), "reference": exp.reference, "features": len(prepared.features)}
    result["paired_vs_ets_mase"] = harness.paired(rows, "m", "ets", "mase")
    result["paired_vs_ets_pinball"] = harness.paired(rows, "m", "ets", "pinball")
    result["seconds"] = round(time.perf_counter() - start, 1)
    harness.save_result(name, TARGET.name, result)
    return result


def summary_line(name: str, r: dict) -> str:
    m, e = r["model"], r["ets"]
    return (
        f"{name:<26} MASE {m['mase']:.3f} (ets {e['mase']:.3f})  MAPE {m['mape']:.1f}  "
        f"pinball {m['pinball_mean']:.1f} (ets {e['pinball_mean']:.1f})  cov {m['coverage']:.2f}  "
        f"vsETS dMASE {r['paired_vs_ets_mase']['mean_diff']:+.3f} "
        f"[{r['paired_vs_ets_mase']['ci_low']:+.3f},{r['paired_vs_ets_mase']['ci_high']:+.3f}]  {r['seconds']}s"
    )


def main(names: list[str]) -> None:
    data = harness.load_data()
    origins = harness.dev_origins(TARGET)
    harness.assert_development(origins, TARGET)
    base = harness.cached_baselines(data, TARGET, origins, "dev")
    print(f"{len(origins)} development origins, {origins[0].date()} to {origins[-1].date()}", flush=True)
    for name in names:
        print(summary_line(name, run_gbm(name, EXPERIMENTS[name], data, origins, base)), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or list(EXPERIMENTS))
