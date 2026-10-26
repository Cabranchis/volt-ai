"""Probability that the daily price passes a threshold, h = 1..14 days ahead.

Usage: python run_spikes.py [--reported]. Development origins by default; --reported runs the single
confirmation on the reported origins (recorded in results/reported_runs.json, once per name).

Events: price above 500 COP/kWh, above 800, and above 1.3 times its mean of the last 30 days.
Model: LightGBM binary on the price model's features plus the absolute level, trained only on rows
whose outcome was known at the origin. Baselines: the base rate seen in training, persistence
(P(event | event now) and P(event | no event now) from training), and the ETS interval read as a
log-normal. Metrics: Brier score, log loss and AUC, pooled over scored origins.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.metrics import log_loss, roc_auc_score

import harness
import run_price
import run_reported
from voltia.features import TARGETS
from voltia.models.backtest import training_mask

TARGET = TARGETS["price_mean_cop_kwh"]
EVENTS = {
    "above_500": ("abs", 500.0),
    "above_800": ("abs", 800.0),
    "rise_1.3x_30d": ("rel", 1.3),
}
PARAMS = {
    "objective": "binary",
    "num_leaves": 15,
    "learning_rate": 0.04,
    "min_data_in_leaf": 100,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.7,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "seed": 20261024,
    "num_threads": 6,
    "deterministic": True,
    "force_row_wise": True,
    "verbosity": -1,
}
ROUNDS = 300
EPS = 1e-4


def event_labels(table: pd.DataFrame, y_log: np.ndarray, mean30_log: np.ndarray, kind: str, value: float) -> np.ndarray:
    """1.0 where the target day's price passes the threshold, NaN where it is not known."""
    threshold = np.full(len(y_log), np.log(value)) if kind == "abs" else mean30_log + np.log(value)
    label = (y_log > threshold).astype(float)
    return np.where(np.isnan(y_log) | np.isnan(threshold), np.nan, label)


def run(origins: list[pd.Timestamp], data: pd.DataFrame, tag: str, base_ets: pd.DataFrame) -> dict:
    exp = run_price.EXPERIMENTS["dispatch+contracts+hydro"]
    prepared = run_price.extended(data, exp)
    table = prepared.table
    price = data[TARGET.name]
    mean30 = np.log(price.rolling(30, min_periods=20).mean())
    m30_origin = mean30.reindex(pd.DatetimeIndex(table["origin"])).to_numpy()
    # absolute level features: the model's features are relative to the recent level
    x = np.hstack([prepared.x, table[["ref_log"]].to_numpy(dtype=np.float32), m30_origin[:, None].astype(np.float32)])
    names = [*prepared.features, "ref_log", "mean30_log"]
    last_price = price.reindex(pd.DatetimeIndex(table["origin"])).to_numpy()
    ets = base_ets.set_index(["origin", "h"])
    results: dict = {}
    for event, (kind, value) in EVENTS.items():
        labels = event_labels(table, prepared.y_log, m30_origin, kind, value)
        threshold_now = np.full(len(table), value) if kind == "abs" else np.exp(m30_origin) * value
        now = (last_price > threshold_now).astype(float)
        records = []
        for origin in origins:
            mask = training_mask(prepared, origin) & ~np.isnan(labels)
            rows = np.flatnonzero(table["origin"].to_numpy() == np.datetime64(origin))
            if mask.sum() < 500 or len(rows) == 0:
                continue
            train = lgb.Dataset(x[mask], label=labels[mask], feature_name=names)
            booster = lgb.train(PARAMS, train, num_boost_round=ROUNDS)
            p_model = booster.predict(x[rows])
            rate = labels[mask].mean()
            on, off = now[mask] == 1, now[mask] == 0
            p_on = labels[mask][on].mean() if on.any() else rate
            p_off = labels[mask][off].mean() if off.any() else rate
            p_persist = np.where(now[rows] == 1, p_on, p_off)
            e = ets.reindex(pd.MultiIndex.from_arrays([table["origin"].to_numpy()[rows], table["h"].to_numpy()[rows]]))
            sigma = (np.log(e["ets90"].to_numpy()) - np.log(e["ets10"].to_numpy())) / (2 * norm.ppf(0.9))
            thr_log = np.log(value) if kind == "abs" else m30_origin[rows] + np.log(value)
            p_ets = 1 - norm.cdf((thr_log - np.log(e["ets50"].to_numpy())) / np.maximum(sigma, 1e-3))
            records.append(
                pd.DataFrame(
                    {
                        "origin": origin,
                        "h": table["h"].to_numpy()[rows],
                        "y": labels[rows],
                        "model": p_model,
                        "base_rate": rate,
                        "persistence": p_persist,
                        "ets": p_ets,
                        "now": now[rows],
                    }
                )
            )
        frame = pd.concat(records, ignore_index=True)
        frame = frame[frame["y"].notna()]
        scored = frame[frame["origin"].isin(sorted(frame["origin"].unique())[harness.N_WARMUP :])]
        out: dict = {"n_rows": len(scored), "event_rate": float(scored["y"].mean())}
        for method in ("model", "base_rate", "persistence", "ets"):
            p = np.clip(scored[method].to_numpy(), EPS, 1 - EPS)
            y = scored["y"].to_numpy()
            out[method] = {
                "brier": float(np.mean((p - y) ** 2)),
                "log_loss": float(log_loss(y, p, labels=[0, 1])) if 0 < y.mean() < 1 else None,
                "auc": float(roc_auc_score(y, p)) if 0 < y.mean() < 1 else None,
            }
        # from-below subset: the event is not happening at the origin
        below = scored[scored["now"] == 0]
        if len(below) and 0 < below["y"].mean() < 1:
            out["from_below"] = {
                "n_rows": len(below),
                "event_rate": float(below["y"].mean()),
                **{
                    m: {
                        "brier": float(np.mean((np.clip(below[m], EPS, 1 - EPS) - below["y"]) ** 2)),
                        "auc": float(roc_auc_score(below["y"], below[m])),
                    }
                    for m in ("model", "base_rate", "persistence", "ets")
                },
            }
        by_origin = scored.groupby("origin").apply(
            lambda g: pd.Series({m: float(np.mean((g[m] - g["y"]) ** 2)) for m in ("model", "persistence", "ets", "base_rate")}),
            include_groups=False,
        )
        for other in ("persistence", "ets", "base_rate"):
            diff = (by_origin["model"] - by_origin[other]).to_numpy()
            rng = np.random.default_rng(7)
            means = rng.choice(diff, size=(4000, len(diff))).mean(axis=1)
            out[f"brier_diff_vs_{other}"] = {
                "mean": float(diff.mean()),
                "ci": [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))],
                "wins": int((diff < 0).sum()),
                "origins": int(len(diff)),
            }
        # reliability: observed frequency by predicted-probability decile
        bins = pd.cut(scored["model"], [0, 0.05, 0.15, 0.3, 0.5, 0.7, 0.9, 1.0], include_lowest=True)
        out["reliability"] = {
            str(k): {"predicted": float(g["model"].mean()), "observed": float(g["y"].mean()), "n": int(len(g))}
            for k, g in scored.groupby(bins, observed=True)
        }
        results[event] = out
        print(
            f"{tag} {event:<14} rate {out['event_rate']:.3f}  Brier model {out['model']['brier']:.4f} "
            f"persist {out['persistence']['brier']:.4f} ets {out['ets']['brier']:.4f} base {out['base_rate']['brier']:.4f}  "
            f"AUC model {out['model']['auc']:.3f} persist {out['persistence']['auc']:.3f} ets {out['ets']['auc']:.3f}",
            flush=True,
        )
    return results


def main(reported: bool) -> None:
    data = harness.load_data()
    start = time.perf_counter()
    if reported:
        name = "spikes"
        origins = run_reported.origins()
        log = run_reported.LOG
        history = json.loads(log.read_text()) if log.exists() else {}
        key = f"price_mean_cop_kwh/{name}"
        if key in history and "--force" not in sys.argv:
            raise SystemExit(f"{key} already ran on the reported origins")
        history[key] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        log.write_text(json.dumps(history, indent=2, sort_keys=True))
        tag = "reported"
        base_ets = pd.read_csv(harness.DATA / "ets_price.csv", parse_dates=["origin"])
    else:
        origins = harness.dev_origins(TARGET)
        harness.assert_development(origins, TARGET)
        tag = "dev"
        base_ets = pd.read_csv(harness.DATA / "ets_price.csv", parse_dates=["origin"])
    results = run(origins, data, tag, base_ets)
    path = harness.RESULTS / "price_mean_cop_kwh" / f"spikes_{tag}.json"
    path.write_text(json.dumps(harness.rounded({"seconds": round(time.perf_counter() - start, 1), "events": results}), indent=2, sort_keys=True))


if __name__ == "__main__":
    main("--reported" in sys.argv)
