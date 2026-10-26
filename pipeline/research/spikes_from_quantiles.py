"""Probability of exceeding a threshold read from the forecast's own P10/P50/P90 (log-normal).

No new model: the calibrated quantiles of the price forecast are turned into P(price > threshold).
Scored like run_spikes.py. Development rows are used to judge it; the reported rows are read once
after the development result is known (post hoc, labelled as such in the ledger).
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.metrics import roc_auc_score

import harness
import run_spikes

Z90 = norm.ppf(0.9)


def probability(rows: pd.DataFrame, prefix: str, thr: np.ndarray) -> np.ndarray:
    mu = np.log(rows[f"{prefix}50"].to_numpy())
    sigma = (np.log(rows[f"{prefix}90"].to_numpy()) - np.log(rows[f"{prefix}10"].to_numpy())) / (2 * Z90)
    return 1 - norm.cdf((np.log(thr) - mu) / np.maximum(sigma, 1e-3))


def score(rows_path: str, data: pd.DataFrame) -> dict:
    rows = pd.read_csv(harness.DATA / rows_path, parse_dates=["origin", "day"])
    rows = rows[(~rows["warmup"]) & rows["calibrated"] & rows["y"].notna()].copy()
    price = data["price_mean_cop_kwh"]
    mean30 = price.rolling(30, min_periods=20).mean()
    rows["mean30"] = mean30.reindex(pd.DatetimeIndex(rows["origin"])).to_numpy()
    rows["last"] = price.reindex(pd.DatetimeIndex(rows["origin"])).to_numpy()
    out = {}
    for event, (kind, value) in run_spikes.EVENTS.items():
        thr = np.full(len(rows), value) if kind == "abs" else rows["mean30"].to_numpy() * value
        y = (rows["y"].to_numpy() > thr).astype(float)
        now = (rows["last"].to_numpy() > thr).astype(float)
        p_on, p_off = y[now == 1].mean(), y[now == 0].mean()
        persistence = np.where(now == 1, p_on, p_off)  # in-sample rates: an optimistic baseline
        entry = {"event_rate": float(y.mean())}
        for name, p in (
            ("forecast_quantiles", probability(rows, "m", thr)),
            ("ets", probability(rows, "ets", thr)),
            ("persistence_in_sample", persistence),
        ):
            p = np.clip(p, 1e-4, 1 - 1e-4)
            entry[name] = {"brier": float(np.mean((p - y) ** 2)), "auc": float(roc_auc_score(y, p))}
        out[event] = entry
    return out


if __name__ == "__main__":
    data = harness.load_data()
    result = {
        "development": score("rows_dispatch+contracts+hydro.csv", data),
        "reported_post_hoc": score("rows_reported_dispatch+contracts+hydro.csv", data),
    }
    path = harness.RESULTS / "price_mean_cop_kwh" / "spikes_from_quantiles.json"
    path.write_text(json.dumps(harness.rounded(result), indent=2, sort_keys=True))
    for period, events in result.items():
        for event, e in events.items():
            q, t, p = e["forecast_quantiles"], e["ets"], e["persistence_in_sample"]
            print(
                f"{period:<18} {event:<14} rate {e['event_rate']:.3f}  Brier quantiles {q['brier']:.4f} "
                f"ets {t['brier']:.4f} persistence {p['brier']:.4f}  AUC {q['auc']:.3f}/{t['auc']:.3f}/{p['auc']:.3f}"
            )
    sys.exit(0)
