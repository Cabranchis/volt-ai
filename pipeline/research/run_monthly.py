"""Mean spot price over the next 30, 31-60 and 61-90 days: can anything beat "it stays where it is"?

Usage: python run_monthly.py [--reported]. Each origin T (the last settled price day) forecasts the
mean daily price of the windows (T+1..T+30), (T+31..T+60), (T+61..T+90) as a ratio to the mean of the
last 30 days. Candidates: persistence (the ratio is 1), the historical median ratio for that month,
ridge on hydrology and climate with residual quantiles, a strongly regularised LightGBM, and an
analog method (the outcomes that followed the most similar past states). Development origins first;
the reported origins run once for the candidates fixed before looking at them.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

import harness
import run_reported
from voltia.features import oni_known
from voltia.models import metrics
from voltia.models.calibration import apply_offset, conformal_offset

WINDOWS = (1, 2, 3)  # months ahead, 30 days each
QS = (0.1, 0.5, 0.9)
FEATURES = [
    "res",
    "res_chg30",
    "res_chg90",
    "inflows30",
    "inflows90",
    "oni",
    "oni_chg3",
    "thermal28",
    "trend_90_365",
    "vol30",
    "dc_rel",
    "doy_sin",
    "doy_cos",
]
ANALOG_FEATURES = ["res", "res_chg30", "inflows90", "oni", "trend_90_365"]


def origin_frame(data: pd.DataFrame) -> pd.DataFrame:
    price = data["price_mean_cop_kwh"]
    lp = np.log(price)
    m30 = np.log(price.rolling(30, min_periods=22).mean())
    m90 = np.log(price.rolling(90, min_periods=65).mean())
    m365 = np.log(price.rolling(365, min_periods=250).mean())
    res = data["reservoir_pct"]
    total = data["gen_total_kwh"]
    thermal = data["gen_thermal_kwh"]
    oni = oni_known(data)
    dc = np.log(data["dispatch_cost"].where(data["dispatch_cost"] > 0))
    frame = pd.DataFrame(
        {
            "m30": m30,
            "res": res,
            "res_chg30": res - res.shift(30),
            "res_chg90": res - res.shift(90),
            "inflows30": data["inflows_pct"].rolling(30, min_periods=22).mean(),
            "inflows90": data["inflows_pct"].rolling(90, min_periods=65).mean(),
            "oni": oni,
            "oni_chg3": oni - oni.shift(91),
            "thermal28": thermal.rolling(28, min_periods=21).sum() / total.rolling(28, min_periods=21).sum(),
            "trend_90_365": m90 - m365,
            "vol30": lp.diff().rolling(30, min_periods=22).std(),
            "dc_rel": dc.rolling(7, min_periods=4).mean().shift(-2) - m30,
            "doy_sin": np.sin(2 * np.pi * data.index.dayofyear / 365.25),
            "doy_cos": np.cos(2 * np.pi * data.index.dayofyear / 365.25),
        },
        index=data.index,
    )
    for k in WINDOWS:
        window_mean = price.rolling(30, min_periods=25).mean().shift(-30 * k)  # mean of T+30(k-1)+1 .. T+30k
        frame[f"y{k}"] = np.log(window_mean) - m30
    return frame


def known_rows(frame: pd.DataFrame, origin: pd.Timestamp, k: int) -> pd.DataFrame:
    """Rows whose whole window k had ended on or before the origin (outcome known at the origin)."""
    cutoff = origin - pd.Timedelta(days=30 * k)
    return frame.loc[:cutoff].dropna(subset=[f"y{k}", *FEATURES])


def predict_origin(frame: pd.DataFrame, origin: pd.Timestamp, k: int) -> dict[str, np.ndarray]:
    """Log-ratio quantiles (P10, P50, P90) per candidate for window k at one origin."""
    train = known_rows(frame, origin, k)
    x_now = frame.loc[[origin], FEATURES]
    out: dict[str, np.ndarray] = {}
    if len(train) < 200 or x_now.isna().any(axis=None):
        return out
    y = train[f"y{k}"].to_numpy()
    out["persistence"] = np.zeros(3)
    spread = np.quantile(y - np.median(y), [QS[0], QS[2]])
    month = origin.month
    same_month = train[train.index.month == month][f"y{k}"]
    seasonal = float(same_month.median()) if len(same_month) >= 20 else 0.0
    out["seasonal_ratio"] = np.array([seasonal + spread[0], seasonal, seasonal + spread[1]])

    scaler = StandardScaler().fit(train[FEATURES])
    xs, xn = scaler.transform(train[FEATURES]), scaler.transform(x_now)
    ridge = Ridge(alpha=300.0).fit(xs, y)
    resid = y - ridge.predict(xs)
    mid = float(ridge.predict(xn)[0])
    lo, hi = np.quantile(resid, [QS[0], QS[2]])
    out["ridge"] = np.array([mid + lo, mid, mid + hi])

    params = {
        "objective": "quantile",
        "num_leaves": 4,
        "learning_rate": 0.03,
        "min_data_in_leaf": 150,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.7,
        "bagging_freq": 1,
        "lambda_l2": 10.0,
        "seed": 20261024,
        "num_threads": 6,
        "deterministic": True,
        "force_row_wise": True,
        "verbosity": -1,
    }
    data = lgb.Dataset(train[FEATURES].to_numpy(dtype=np.float32), label=y)
    out["lgbm"] = np.sort(
        [
            float(lgb.train({**params, "alpha": q}, data, num_boost_round=150).predict(x_now.to_numpy(dtype=np.float32))[0])
            for q in QS
        ]
    )

    a_scaler = StandardScaler().fit(train[ANALOG_FEATURES])
    distance = np.linalg.norm(a_scaler.transform(train[ANALOG_FEATURES]) - a_scaler.transform(x_now[ANALOG_FEATURES]), axis=1)
    # one analog per month at most: neighbours from the same weeks are the same event
    order = np.argsort(distance)
    chosen, months = [], set()
    for i in order:
        key = (train.index[i].year, train.index[i].month)
        if key in months:
            continue
        months.add(key)
        chosen.append(i)
        if len(chosen) == 12:
            break
    out["analog"] = np.quantile(y[chosen], QS)
    return out


def run(origins: list[pd.Timestamp], data: pd.DataFrame, tag: str) -> dict:
    frame = origin_frame(data)
    price = data["price_mean_cop_kwh"]
    records = []
    for origin in origins:
        for k in WINDOWS:
            end = origin + pd.Timedelta(days=30 * k)
            window = price.loc[origin + pd.Timedelta(days=30 * (k - 1) + 1) : end]
            if len(window) < 25 or window.isna().mean() > 0.2:
                continue
            truth = float(window.mean())
            m30 = float(np.exp(frame.loc[origin, "m30"]))
            for name, q in predict_origin(frame, origin, k).items():
                level = m30 * np.exp(q)
                records.append({"origin": origin, "k": k, "method": name, "p10": level[0], "p50": level[1], "p90": level[2], "y": truth, "m30": m30})
    table = pd.DataFrame(records)
    # online conformal widening per method and window, from earlier origins whose window had ended
    adjusted = []
    for (method, k), part in table.groupby(["method", "k"]):
        part = part.sort_values("origin").copy()
        for i, row in part.iterrows():
            past = part[(part["origin"] < row["origin"]) & (part["origin"] + pd.Timedelta(days=30 * k) <= row["origin"])]
            if len(past) >= 4:
                off = conformal_offset(np.log(past["p10"]), np.log(past["p90"]), np.log(past["y"]))
                lo, mid, hi = np.exp(apply_offset(np.log(row[["p10", "p50", "p90"]].to_numpy(dtype=float))[None, :], off))[0]
            else:
                lo, mid, hi = row["p10"], row["p50"], row["p90"]
            part.loc[i, ["c10", "c50", "c90"]] = [lo, mid, hi]
            part.loc[i, "calibrated"] = len(past) >= 4
        adjusted.append(part)
    table = pd.concat(adjusted, ignore_index=True)
    scored = table[(table["origin"] >= sorted(table["origin"].unique())[harness.N_WARMUP]) & table["calibrated"].astype(bool)]
    results: dict = {}
    for (method, k), part in scored.groupby(["method", "k"]):
        y = part["y"].to_numpy()
        pins = [metrics.pinball(y, part[c].to_numpy(), a) for c, a in zip(("c10", "c50", "c90"), QS, strict=True)]
        results.setdefault(method, {})[f"window_{k}"] = {
            "n_origins": int(len(part)),
            "mape": metrics.mape(y, part["c50"].to_numpy()),
            "pinball_mean": float(np.mean(pins)),
            "coverage": metrics.coverage(y, part["c10"].to_numpy(), part["c90"].to_numpy()),
            "bias_pct": float(np.mean(part["c50"].to_numpy() / y - 1) * 100),
        }
    # paired against persistence per origin on pinball
    for method in results:
        if method == "persistence":
            continue
        for k in WINDOWS:
            a = scored[(scored["method"] == method) & (scored["k"] == k)].set_index("origin")
            b = scored[(scored["method"] == "persistence") & (scored["k"] == k)].set_index("origin")
            both = a.index.intersection(b.index)
            if len(both) < 5:
                continue
            da = np.array([np.mean([metrics.pinball([a.loc[o, "y"]], [a.loc[o, c]], q) for c, q in zip(("c10", "c50", "c90"), QS, strict=True)]) for o in both])
            db = np.array([np.mean([metrics.pinball([b.loc[o, "y"]], [b.loc[o, c]], q) for c, q in zip(("c10", "c50", "c90"), QS, strict=True)]) for o in both])
            diff = da - db
            rng = np.random.default_rng(7)
            means = rng.choice(diff, size=(4000, len(diff))).mean(axis=1)
            results[method][f"window_{k}"]["pinball_diff_vs_persistence"] = {
                "mean": float(diff.mean()),
                "ci": [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))],
                "wins": int((diff < 0).sum()),
                "origins": int(len(diff)),
            }
    for method, windows in results.items():
        print(
            tag,
            f"{method:<15}",
            " | ".join(f"w{k}: MAPE {windows[f'window_{k}']['mape']:.1f} pin {windows[f'window_{k}']['pinball_mean']:.1f} cov {windows[f'window_{k}']['coverage']:.2f}" for k in WINDOWS if f"window_{k}" in windows),
            flush=True,
        )
    return results


def main(reported: bool) -> None:
    data = harness.load_data()
    start = time.perf_counter()
    if reported:
        log = run_reported.LOG
        history = json.loads(log.read_text()) if log.exists() else {}
        key = "price_mean_cop_kwh/monthly"
        if key in history and "--force" not in sys.argv:
            raise SystemExit(f"{key} already ran on the reported origins")
        history[key] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        log.write_text(json.dumps(history, indent=2, sort_keys=True))
        origins = run_reported.origins()
        tag = "reported"
    else:
        from voltia.features import TARGETS

        origins = harness.dev_origins(TARGETS["price_mean_cop_kwh"])
        # outcomes up to 90 days ahead must also precede the reported period
        origins = [o for o in origins if o + pd.Timedelta(days=90) < harness.REPORTED_FIRST]
        tag = "dev"
    results = run(origins, data, tag)
    path = harness.RESULTS / "price_mean_cop_kwh" / f"monthly_{tag}.json"
    path.write_text(json.dumps(harness.rounded({"seconds": round(time.perf_counter() - start, 1), "origins": len(origins), "methods": results}), indent=2, sort_keys=True))


if __name__ == "__main__":
    main("--reported" in sys.argv)
