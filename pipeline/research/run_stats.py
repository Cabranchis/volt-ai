"""Classical statistical forecasters (statsforecast) on log price: AutoETS, AutoARIMA, MSTL, Theta.

Each model is fitted on the last 3 years up to the origin and gives an 80 % interval, like the ETS
baseline. Usage: python run_stats.py [name ...].
"""

from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd
from statsforecast import StatsForecast
from statsforecast.models import AutoARIMA, AutoETS, AutoTheta, MSTL

import harness
import run_price
from voltia.features import TARGETS

TARGET = TARGETS["price_mean_cop_kwh"]
WINDOW = 1092

MODELS = {
    "sf_autoets": lambda: AutoETS(season_length=7),
    "sf_autoarima": lambda: AutoARIMA(season_length=7),
    "sf_autotheta": lambda: AutoTheta(season_length=7),
    "sf_mstl": lambda: MSTL(season_length=[7, 365], trend_forecaster=AutoETS(model="ZZN")),
}


def forecast(name: str, series: pd.Series, origin: pd.Timestamp) -> pd.DataFrame:
    seen = series.loc[:origin].iloc[-WINDOW:].interpolate(limit_direction="both")
    frame = pd.DataFrame({"unique_id": "p", "ds": seen.index, "y": np.log(seen.to_numpy())})
    model = MODELS[name]()
    sf = StatsForecast(models=[model], freq="D", n_jobs=1)
    out = sf.forecast(df=frame, h=TARGET.horizon, level=[80])
    alias = model.alias if hasattr(model, "alias") else type(model).__name__
    cols = [c for c in out.columns if c.startswith(alias)]
    mid = next(c for c in cols if "lo" not in c and "hi" not in c)
    lo = next(c for c in cols if c.endswith("lo-80"))
    hi = next(c for c in cols if c.endswith("hi-80"))
    return pd.DataFrame(
        {
            "origin": origin,
            "h": np.arange(1, TARGET.horizon + 1),
            "day": pd.DatetimeIndex(out["ds"]),
            "q10_log": out[lo].to_numpy(),
            "q50_log": out[mid].to_numpy(),
            "q90_log": out[hi].to_numpy(),
        }
    )


def main(names: list[str]) -> None:
    data = harness.load_data()
    origins = harness.dev_origins(TARGET)
    harness.assert_development(origins, TARGET)
    base = harness.cached_baselines(data, TARGET, origins, "dev")
    series = data[TARGET.name]
    for name in names:
        start = time.perf_counter()
        pred = pd.concat([forecast(name, series, o) for o in origins], ignore_index=True)
        rows = harness.finish_rows(pred, data, TARGET, base)
        rows.to_csv(harness.DATA / f"rows_{name}.csv", index=False)
        result = harness.score(rows)
        result["experiment"] = {"name": name, "library": "statsforecast", "window_days": WINDOW}
        result["paired_vs_ets_mase"] = harness.paired(rows, "m", "ets", "mase")
        result["paired_vs_ets_pinball"] = harness.paired(rows, "m", "ets", "pinball")
        result["seconds"] = round(time.perf_counter() - start, 1)
        harness.save_result(name, TARGET.name, result)
        print(run_price.summary_line(name, result), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or list(MODELS))
