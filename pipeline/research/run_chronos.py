"""Chronos-2 (foundation model) zero-shot on the price, with and without covariates.

Usage: python run_chronos.py [variant ...]. The context is the last CONTEXT days up to the origin;
the dispatch cost of the days already priced by A = T + 3 enters as a known future covariate.
"""

from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

import harness
import run_price
from voltia.features import TARGETS

TARGET = TARGETS["price_mean_cop_kwh"]
CONTEXT = 1000
MODEL = "amazon/chronos-2"

VARIANTS = {
    "chronos2_uni": {"past": [], "future": []},
    "chronos2_dc": {"past": ["dc"], "future": ["dc"]},
    "chronos2_cov": {"past": ["dc", "res", "inflows", "demand"], "future": ["dc"]},
    # LoRA fine-tuning on the price history up to each refit date, refitted every REFIT origins.
    "chronos2_ft": {"past": [], "future": [], "finetune": True},
}
REFIT = 6
FT_STEPS = 300


def covariates(data: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "dc": np.log(data["dispatch_cost"].where(data["dispatch_cost"] > 0)),
            "res": data["reservoir_pct"].astype(float),
            "inflows": data["inflows_pct"].astype(float),
            "demand": np.log(data["demand_kwh"].where(data["demand_kwh"] > 0)),
        }
    )


def forecast(pipe, data: pd.DataFrame, cov: pd.DataFrame, origin: pd.Timestamp, spec: dict) -> pd.DataFrame:
    start = origin - pd.Timedelta(days=CONTEXT)
    ctx = data.loc[start:origin]
    frame = {
        "item_id": "p",
        "timestamp": ctx.index,
        "target": np.log(ctx["price_mean_cop_kwh"].interpolate(limit_direction="both").to_numpy()),
    }
    for name in spec["past"]:
        frame[name] = cov.loc[start:origin, name].to_numpy()
    past = pd.DataFrame(frame)
    future = None
    if spec["future"]:
        idx = pd.date_range(origin + pd.Timedelta(days=1), periods=TARGET.horizon, freq="D")
        known_until = harness.known_through("dispatch_cost", origin + pd.Timedelta(days=harness.SETTLE_LAG))
        values = {"item_id": "p", "timestamp": idx}
        for name in spec["future"]:
            v = cov[name].reindex(idx).to_numpy().copy()
            v[idx > known_until] = np.nan
            values[name] = v
        future = pd.DataFrame(values)
    out = pipe.predict_df(
        past,
        future_df=future,
        id_column="item_id",
        timestamp_column="timestamp",
        target="target",
        prediction_length=TARGET.horizon,
        quantile_levels=[0.1, 0.5, 0.9],
    )
    return pd.DataFrame(
        {
            "origin": origin,
            "h": np.arange(1, TARGET.horizon + 1),
            "day": pd.DatetimeIndex(out["timestamp"]),
            "q10_log": out["0.1"].to_numpy(),
            "q50_log": out["0.5"].to_numpy(),
            "q90_log": out["0.9"].to_numpy(),
        }
    )


def main(names: list[str]) -> None:
    import torch
    from chronos import Chronos2Pipeline

    data = harness.load_data()
    origins = harness.dev_origins(TARGET)
    harness.assert_development(origins, TARGET)
    base = harness.cached_baselines(data, TARGET, origins, "dev")
    pipe = Chronos2Pipeline.from_pretrained(MODEL, device_map="cuda" if torch.cuda.is_available() else "cpu")
    cov = covariates(data)
    for name in names:
        start = time.perf_counter()
        spec = VARIANTS[name]
        frames = []
        tuned = pipe
        for i, origin in enumerate(origins):
            if spec.get("finetune") and i % REFIT == 0:
                series = np.log(data.loc[:origin, "price_mean_cop_kwh"].interpolate(limit_direction="both").to_numpy())
                tuned = pipe.fit(
                    inputs=[{"target": series[-CONTEXT * 2 :]}],
                    prediction_length=TARGET.horizon,
                    finetune_mode="lora",
                    learning_rate=1e-5,
                    num_steps=FT_STEPS,
                    batch_size=32,
                    output_dir=harness.DATA / "chronos_ft",
                )
            frames.append(forecast(tuned, data, cov, origin, spec))
        pred = pd.concat(frames, ignore_index=True)
        rows = harness.finish_rows(pred, data, TARGET, base)
        rows.to_csv(harness.DATA / f"rows_{name}.csv", index=False)
        result = harness.score(rows)
        result["experiment"] = {"name": name, "model": MODEL, **VARIANTS[name], "context_days": CONTEXT}
        result["paired_vs_ets_mase"] = harness.paired(rows, "m", "ets", "mase")
        result["paired_vs_ets_pinball"] = harness.paired(rows, "m", "ets", "pinball")
        result["seconds"] = round(time.perf_counter() - start, 1)
        harness.save_result(name, TARGET.name, result)
        print(run_price.summary_line(name, result), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or list(VARIANTS))
