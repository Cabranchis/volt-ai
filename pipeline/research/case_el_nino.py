"""Case study (El Nino 2023-24 vs 2026): re-run the production price backtest and keep every row.

The stored run keeps only metrics per origin. This script repeats the same backtest (same config,
same anchored origins) on a local SQLite copy of the data and writes each origin's calibrated
P10/P50/P90 next to the actual and the two baselines, so the forecasts can be drawn. It first
checks that it reproduces the production MASE per origin.

    DATABASE_URL=sqlite:///data/voltia.sqlite uv run python research/case_el_nino.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
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

OUT = Path(__file__).parent / "results" / "case_el_nino_rows.json"
NAME = "price_mean_cop_kwh"
API = "https://voltia-xi-five.vercel.app/api/v1/model"


def main() -> None:
    if db.make_engine().dialect.name != "sqlite":
        sys.exit("refusing to run against a non-SQLite database (set DATABASE_URL)")
    hist = complete_daily(db.read_series(db.make_engine()))
    spec = TARGETS[NAME]
    cfg = BacktestConfig()
    end = last_settled_day(hist, [NAME])
    planned = anchored_origins(pd.Timestamp(cfg.anchor), end, spec.horizon, cfg.step_days, cfg.n_warmup)
    origins = [observed_origin(hist, [NAME], o) for o in planned]
    config = ModelConfig(reference=REFERENCES[NAME], params=GBMParams())
    prepared = prepare(hist, spec, config)
    rows = backtest_target(hist, prepared, origins, cfg.n_warmup, config, cfg)
    rows = rows[~rows["warmup"]]

    prod_run = json.load(urllib.request.urlopen(API))
    prod = prod_run["metrics"]["targets"][NAME]["by_origin"]
    prod_mase = {p["origin"]: p["model_mase"] for p in prod}
    print("columns:", list(rows.columns))
    out = []
    worst = 0.0
    compared = 0
    for origin, part in rows.groupby("origin"):
        key = str(origin.date())
        ok = part["y"].notna()
        mase = float((np.abs(part.loc[ok, "m50"] - part.loc[ok, "y"]) / part.loc[ok, "scale"]).mean())
        if key in prod_mase:
            worst = max(worst, abs(mase - prod_mase[key]))
            compared += 1
        out.append({
            "origin": key,
            "rows": [
                {"day": str(pd.Timestamp(r.day).date()), "h": int(r.h), "y": None if pd.isna(r.y) else float(r.y),
                 "p10": float(r.m10), "p50": float(r.m50), "p90": float(r.m90),
                 "ets": float(r.ets50), "naive": float(r.sn50)}
                for r in part.itertuples()
            ],
        })
    missing = sorted(set(prod_mase) - {o["origin"] for o in out})
    print("max |MASE - production| over origins:", round(worst, 4), f"({compared} compared)")
    if missing or compared != len(prod_mase) or worst > 1e-3:
        sys.exit(f"does not reproduce production: missing origins {missing}, worst difference {worst}")
    OUT.write_text(json.dumps({"target": NAME, "runId": prod_run["runId"], "origins": out}, separators=(",", ":")))
    print("wrote", OUT, len(out), "origins")


if __name__ == "__main__":
    main()
