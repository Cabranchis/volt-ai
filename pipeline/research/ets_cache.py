"""ETS(A,Ad,A) forecasts for the price at many origins, cached on disk for the hybrid experiments.

Each origin's forecast uses only the last three years up to that origin, exactly like the
production baseline. Run once: `uv run python ets_cache.py`; later runs add missing origins.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import harness
from voltia.features import TARGETS
from voltia.models.baselines import ets_forecast

TARGET = TARGETS["price_mean_cop_kwh"]
PATH = harness.DATA / "ets_price.csv"
STEP = 1
FIRST = pd.Timestamp("2019-01-01")  # a year of history before the first origin


def one(series: pd.Series, origin: pd.Timestamp) -> pd.DataFrame:
    out = ets_forecast(series, origin, TARGET.horizon, True, 1092)
    frame = pd.DataFrame({"origin": origin, "h": np.arange(1, TARGET.horizon + 1)})
    frame["ets10"], frame["ets50"], frame["ets90"] = out[:, 0], out[:, 1], out[:, 2]
    return frame


def build(last_origin: pd.Timestamp) -> pd.DataFrame:
    data = harness.load_data()
    series = data[TARGET.name]
    wanted = pd.date_range(FIRST, last_origin, freq=f"{STEP}D")
    have = pd.read_csv(PATH, parse_dates=["origin"]) if PATH.exists() else pd.DataFrame(columns=["origin"])
    todo = [o for o in wanted if o not in set(have["origin"])]
    print(f"{len(todo)} origins to fit", flush=True)
    start = time.perf_counter()
    parts = Parallel(n_jobs=6)(delayed(one)(series, o) for o in todo)
    table = pd.concat([have, *parts], ignore_index=True).sort_values(["origin", "h"])
    table.to_csv(PATH, index=False)
    print(f"done in {time.perf_counter() - start:.0f}s -> {PATH}", flush=True)
    return table


if __name__ == "__main__":
    data = harness.load_data()
    last = data["price_mean_cop_kwh"].last_valid_index() - pd.Timedelta(days=TARGET.horizon)
    build(last)
