"""N-HiTS (neuralforecast) on log price with historical covariates, refitted every REFIT origins.

The model for an origin was fitted at the latest refit date on or before it, on data up to that
date, then applied to the window that ends at the origin. Usage: python run_nhits.py [name].
"""

from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd
import torch

import harness
import run_price
from voltia.features import TARGETS

TARGET = TARGETS["price_mean_cop_kwh"]
REFIT = 6  # origins between refits (about 180 days)
INPUT = 120
EXOG = ["dc", "res", "inflows", "demand"]


def long_frame(data: pd.DataFrame, end: pd.Timestamp) -> pd.DataFrame:
    d = data.loc[:end]
    frame = pd.DataFrame(
        {
            "unique_id": "p",
            "ds": d.index,
            "y": np.log(d["price_mean_cop_kwh"].interpolate(limit_direction="both").to_numpy()),
            "dc": np.log(d["dispatch_cost"].where(d["dispatch_cost"] > 0)).ffill().to_numpy(),
            "res": d["reservoir_pct"].ffill().to_numpy(),
            "inflows": d["inflows_pct"].ffill().to_numpy(),
            "demand": np.log(d["demand_kwh"].where(d["demand_kwh"] > 0)).ffill().to_numpy(),
        }
    )
    return frame.dropna().reset_index(drop=True)


def make_model(steps: int, seed: int):
    from neuralforecast.losses.pytorch import MQLoss
    from neuralforecast.models import NHITS

    return NHITS(
        h=TARGET.horizon,
        input_size=INPUT,
        hist_exog_list=EXOG,
        loss=MQLoss(quantiles=[0.1, 0.5, 0.9]),
        max_steps=steps,
        learning_rate=1e-3,
        scaler_type="robust",
        random_seed=seed,
        batch_size=32,
        enable_progress_bar=False,
        enable_model_summary=False,
        logger=False,
        accelerator="gpu" if torch.cuda.is_available() else "cpu",
    )


def main(name: str = "nhits_exog", steps: int = 400) -> None:
    from neuralforecast import NeuralForecast

    data = harness.load_data()
    origins = harness.dev_origins(TARGET)
    harness.assert_development(origins, TARGET)
    base = harness.cached_baselines(data, TARGET, origins, "dev")
    start = time.perf_counter()
    frames = []
    nf = None
    for i, origin in enumerate(origins):
        if i % REFIT == 0:
            nf = NeuralForecast(models=[make_model(steps, 20261024)], freq="D")
            nf.fit(df=long_frame(data, origin))
        out = nf.predict(df=long_frame(data, origin))
        cols = [c for c in out.columns if c.startswith("NHITS")]
        pick = lambda tags: next((c for c in cols if any(c.endswith(t) for t in tags)), None)  # noqa: E731
        lo, mid, hi = pick(("-lo-80.0", "-lo-80", "q-0.1")), pick(("-median", "q-0.5", "-0.5")), pick(("-hi-80.0", "-hi-80", "q-0.9"))
        if None in (lo, mid, hi):
            raise RuntimeError(f"unexpected quantile columns: {cols}")
        frames.append(
            pd.DataFrame(
                {
                    "origin": origin,
                    "h": np.arange(1, TARGET.horizon + 1),
                    "day": pd.DatetimeIndex(out["ds"]),
                    "q10_log": out[lo].to_numpy(),
                    "q50_log": out[mid].to_numpy(),
                    "q90_log": out[hi].to_numpy(),
                }
            )
        )
    rows = harness.finish_rows(pd.concat(frames, ignore_index=True), data, TARGET, base)
    rows.to_csv(harness.DATA / f"rows_{name}.csv", index=False)
    result = harness.score(rows)
    result["experiment"] = {"name": name, "library": "neuralforecast", "model": "NHITS", "steps": steps, "refit_origins": REFIT, "exog": EXOG}
    result["paired_vs_ets_mase"] = harness.paired(rows, "m", "ets", "mase")
    result["paired_vs_ets_pinball"] = harness.paired(rows, "m", "ets", "pinball")
    result["seconds"] = round(time.perf_counter() - start, 1)
    harness.save_result(name, TARGET.name, result)
    print(run_price.summary_line(name, result), flush=True)


if __name__ == "__main__":
    main()
