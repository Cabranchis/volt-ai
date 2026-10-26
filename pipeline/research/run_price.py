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
import zoo
from voltia.features import MARKET_FEATURES, TARGETS
from voltia.models.backtest import ModelConfig, Prepared, prepare, training_mask
from voltia.models.gbm import GBMParams

TARGET = TARGETS["demand_kwh" if "--demand" in sys.argv else "price_mean_cop_kwh"]
PARAMS = GBMParams(num_threads=6)


@dataclass(frozen=True)
class GBMExperiment:
    blocks: tuple[str, ...] = ()
    reference: str = "last"
    params: GBMParams = PARAMS
    lag_overrides: dict[str, int] = field(default_factory=dict)
    drop: tuple[str, ...] = ()
    family: str = "lightgbm"
    options: dict = field(default_factory=dict)


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
FS1 = ("dispatch", "contracts", "hydro_now")
EXPERIMENTS.update(
    {
        "fs1_xgb": GBMExperiment(blocks=FS1, family="xgboost"),
        "fs1_cat": GBMExperiment(blocks=FS1, family="catboost"),
        "fs1_qrf": GBMExperiment(blocks=FS1, family="quantile_forest"),
        "fs1_linq": GBMExperiment(blocks=FS1, family="linear_quantile"),
        "fs1_ref_level7": GBMExperiment(blocks=FS1, reference="level7"),
        "fs1_ref_sn": GBMExperiment(blocks=FS1, reference="seasonal_naive"),
        "fs1_leaves7": GBMExperiment(blocks=FS1, options={"num_leaves": 7}),
        "fs1_leaves31": GBMExperiment(blocks=FS1, options={"num_leaves": 31}),
        "fs1_slow": GBMExperiment(blocks=FS1, options={"learning_rate": 0.02, "num_boost_round": 800}),
        "fs1_minleaf50": GBMExperiment(blocks=FS1, options={"min_data_in_leaf": 50}),
        "fs1_minleaf200": GBMExperiment(blocks=FS1, options={"min_data_in_leaf": 200}),
    }
)
EXPERIMENTS.update(
    {
        "d_current": GBMExperiment(),
        "d_xgb": GBMExperiment(family="xgboost"),
        "d_cat": GBMExperiment(family="catboost"),
        "d_leaves31": GBMExperiment(options={"num_leaves": 31}),
        "d_slow": GBMExperiment(options={"learning_rate": 0.02, "num_boost_round": 800}),
        "d_hl1460": GBMExperiment(family="xgboost", options={"halflife_days": 1460}),
        "d_ref_level7": GBMExperiment(reference="level7"),
    }
)
FS2 = (*FS1, "nowcast")
EXPERIMENTS.update(
    {
        "fs2_xgb": GBMExperiment(blocks=FS2, family="xgboost"),
        "fs2_lgb": GBMExperiment(blocks=FS2),
        "fs1_xgb_hybrid": GBMExperiment(blocks=FS1, family="xgboost", reference="ets"),
        "fs2_xgb_hybrid": GBMExperiment(blocks=FS2, family="xgboost", reference="ets"),
        "fs1_xgb_hl730": GBMExperiment(blocks=FS1, family="xgboost", options={"halflife_days": 730}),
        "fs1_xgb_hl1460": GBMExperiment(blocks=FS1, family="xgboost", options={"halflife_days": 1460}),
    }
)


def forecast_origin(prepared: Prepared, origin: pd.Timestamp, exp: GBMExperiment) -> pd.DataFrame:
    """Raw quantile forecasts (log units) for one origin from the experiment's model family."""
    mask = training_mask(prepared, origin)
    rows = np.flatnonzero(prepared.table["origin"].to_numpy() == np.datetime64(origin))
    options = dict(exp.options)
    halflife = options.pop("halflife_days", None)
    if halflife:
        age = (np.datetime64(origin) - prepared.table["day"].to_numpy()[mask]).astype("timedelta64[D]").astype(float)
        options["sample_weight"] = 0.5 ** (age / halflife)
    q = zoo.fit_predict(
        exp.family, prepared.x[mask], prepared.z[mask], prepared.x[rows], prepared.features, **options
    )
    q = q + prepared.offset_log[rows, None]
    return pd.DataFrame(
        {
            "origin": origin,
            "h": prepared.table["h"].to_numpy()[rows],
            "day": prepared.table["day"].to_numpy()[rows],
            "q10_log": q[:, 0],
            "q50_log": q[:, 1],
            "q90_log": q[:, 2],
        }
    )


def with_ets_reference(prepared: Prepared) -> Prepared:
    """Target relative to the ETS median at the same (origin, h); adds the ETS view as a feature."""
    ets = pd.read_csv(harness.DATA / "ets_price.csv", parse_dates=["origin"])
    key = pd.MultiIndex.from_arrays([prepared.table["origin"], prepared.table["h"]])
    ets50 = ets.set_index(["origin", "h"])["ets50"].reindex(key).to_numpy()
    offset = np.log(ets50)
    rel = (offset - prepared.table["ref_log"].to_numpy()).astype(np.float32)
    x = np.hstack([prepared.x, rel[:, None]])
    return replace(prepared, x=x, offset_log=offset, features=[*prepared.features, "ets_rel"])


def extended(data: pd.DataFrame, exp: GBMExperiment) -> Prepared:
    base_reference = "last" if exp.reference == "ets" else exp.reference
    prepared = prepare(data, TARGET, ModelConfig(reference=base_reference, params=exp.params))  # type: ignore[arg-type]
    # Production now ships the market features; the experiments add them block by block, so the
    # base here is the feature set the experiments were defined against.
    shipped = set(MARKET_FEATURES.get(TARGET.name, []))
    if shipped:
        keep = [i for i, n in enumerate(prepared.features) if n not in shipped]
        prepared = replace(prepared, x=prepared.x[:, keep], features=[prepared.features[i] for i in keep])
    if exp.reference == "ets":
        prepared = with_ets_reference(prepared)
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
    frames = []
    for origin in origins:
        frames.append(forecast_origin(prepared, origin, exp))
    rows = harness.finish_rows(pd.concat(frames, ignore_index=True), data, TARGET, base)
    rows.to_csv(harness.DATA / f"rows_{name}.csv", index=False)
    result = harness.score(rows)
    result["target"] = TARGET.name
    result["experiment"] = {"name": name, "blocks": list(exp.blocks), "reference": exp.reference, "features": len(prepared.features), "family": exp.family, "options": exp.options}
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
    main([a for a in sys.argv[1:] if not a.startswith("--")] or list(EXPERIMENTS))
