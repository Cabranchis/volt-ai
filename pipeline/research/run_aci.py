"""Adaptive conformal inference for the P10-P90 band of the price and the demand.

Production calibrates each horizon bucket with the CQR offsets of every past origin, equal weights
(`calibrate_online`). A band that is too short for a while stays too short until enough new outcomes
dilute the old scores. Adaptive conformal inference (Gibbs and Candes, 2021) corrects that online: it
keeps, per bucket and per tail, the level `alpha` at which the conformal quantile of the past scores is
taken, and after every outcome it moves the level, `alpha <- alpha + gamma * (0.1 - miss)`, where
`miss` is 1 if the outcome fell outside that tail of the band that was issued. Misses make the next
band wider, hits let it shrink back. With `gamma = 0` the level never moves and the result is exactly
the production calibration (asserted).

Three calibrations of the same raw quantiles are compared, on the dense backtest (origins 7 days
apart, `run_dense_raw.py`, which keeps the raw quantiles and the warm-up origins that production also
calibrates on):
    production   gamma = 0
    aci_005      gamma = 0.005 (the value of the reference paper)
    aci_020      gamma = 0.02
Each past outcome updates the level once, in the order of the day it refers to, and only when it was
issued with a calibrated band; it counts only from the day it is known (`day <= origin`, the rule
production uses). The level is kept in [0.001, 0.5].

Decision rule, written before the first run, for each target and each `gamma`. The calibration is a
candidate for production only if all three hold on the scored origins (after the warm-up):
  1. its overall coverage of the P10-P90 band is between 0.78 and 0.84;
  2. the mean coverage of its worst quarter of windows of 8 consecutive origins is closer to 0.80 than
     the production one;
  3. its mean pinball loss (P10, P50, P90) is not clearly worse: the paired per-origin difference
     (new minus production) does not have a 95 % block-bootstrap interval entirely above zero.
Otherwise the result is negative, it is recorded as such and production does not change. Nothing
else is read into the result. Earlier calibrations that adapt to the regime (recency weights,
volatility scaling, same-regime origins; docs/model-experiments.md) did not win; this one adapts to
the misses themselves, which is different, but the same standard applies.

    uv run python research/run_aci.py price|demand

Reads research/results/dense_raw_<target>.json (run_dense_raw.py). Writes
research/results/aci_<target>.json. No database, no network.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from voltia.features import TARGETS
from voltia.models.backtest import block_bootstrap_ci
from voltia.models.calibration import _conformal_quantile

HERE = Path(__file__).parent
NAMES = {"price": "price_mean_cop_kwh", "demand": "demand_kwh"}
NOMINAL = 0.10  # per tail
LEVEL_RANGE = (0.001, 0.5)
MIN_ORIGINS = 4  # BacktestConfig.min_calibration_origins
WINDOW = 8  # origins per rolling window, about two months
BLOCK = 6
GAMMAS = {"production": 0.0, "aci_005": 0.005, "aci_020": 0.02}
COVERAGE_RANGE = (0.78, 0.84)


def calibrate_aci(
    rows: pd.DataFrame, buckets: list[str], gamma: float, min_origins: int = MIN_ORIGINS
) -> pd.DataFrame:
    """Add `c10`, `c90` (the calibrated band, in the units of the target) and `calibrated`.

    `rows` has origin, day, bucket, y, q10_log, q50_log, q90_log. With gamma = 0 the band is the one of
    `voltia.models.backtest.calibrate_online`.
    """
    rows = rows.sort_values(["origin", "h"]).reset_index(drop=True)
    y_log = np.log(rows["y"].to_numpy())
    q10, q50, q90 = (rows[c].to_numpy(dtype=float) for c in ("q10_log", "q50_log", "q90_log"))
    lower_score, upper_score = q10 - y_log, y_log - q90
    out_lo, out_hi = q10.copy(), q90.copy()
    calibrated = np.zeros(len(rows), dtype=bool)
    level = {(b, tail): NOMINAL for b in buckets for tail in ("lo", "hi")}
    pending: list[int] = []  # issued rows whose outcome has not updated the level yet
    origin_values = rows["origin"].to_numpy()
    day_values = rows["day"].to_numpy()
    bucket_values = rows["bucket"].to_numpy()
    for origin in sorted(rows["origin"].unique()):
        here = np.flatnonzero(origin_values == origin)
        known = [i for i in pending if day_values[i] <= origin]
        for i in sorted(known, key=lambda j: (day_values[j], origin_values[j])):
            b = bucket_values[i]
            for tail, miss in (("lo", y_log[i] < out_lo[i]), ("hi", y_log[i] > out_hi[i])):
                moved = level[(b, tail)] + gamma * (NOMINAL - float(miss))
                level[(b, tail)] = float(np.clip(moved, *LEVEL_RANGE))
        pending = [i for i in pending if day_values[i] > origin]
        past = np.flatnonzero((origin_values < origin) & (day_values <= origin))
        enough = len(np.unique(origin_values[past])) >= min_origins
        for b in buckets:
            sel = here[bucket_values[here] == b]
            if len(sel) == 0:
                continue
            lower = upper = 0.0
            if enough:
                mine = past[bucket_values[past] == b]
                if len(mine):
                    lower = _conformal_quantile(lower_score[mine], level[(b, "lo")])
                    upper = _conformal_quantile(upper_score[mine], level[(b, "hi")])
            out_lo[sel] = np.minimum(q10[sel] - lower, q50[sel])
            out_hi[sel] = np.maximum(q90[sel] + upper, q50[sel])
            if enough:
                calibrated[sel] = True
                pending.extend(sel.tolist())
    rows = rows.copy()
    rows["c10"], rows["c90"] = np.exp(out_lo), np.exp(out_hi)
    rows["calibrated"] = calibrated
    return rows


def pinball_mean(frame: pd.DataFrame, lo: str, hi: str) -> pd.Series:
    """Mean pinball loss of P10, P50, P90 per origin; the P50 is the model's own, unchanged."""
    y = frame["y"]
    p50 = frame["m50"]
    loss = (
        np.maximum(0.1 * (y - frame[lo]), -0.9 * (y - frame[lo]))
        + np.maximum(0.5 * (y - p50), -0.5 * (y - p50))
        + np.maximum(0.9 * (y - frame[hi]), -0.1 * (y - frame[hi]))
    ) / 3
    return loss.groupby(frame["origin"]).mean()


def window_coverage(inside: pd.Series, origins: pd.Series, window: int = WINDOW) -> pd.Series:
    """Coverage in each run of `window` consecutive origins."""
    per_origin = inside.groupby(origins).mean().sort_index()
    return per_origin.rolling(window).mean().dropna()


def worst_quarter(coverage: pd.Series) -> float:
    k = max(1, int(np.ceil(0.25 * len(coverage))))
    return float(coverage.sort_values().iloc[:k].mean())


def summarise(scored: pd.DataFrame, lo: str, hi: str) -> dict[str, float]:
    inside = (scored["y"] >= scored[lo]) & (scored["y"] <= scored[hi])
    windows = window_coverage(inside, scored["origin"])
    return {
        "coverage": float(inside.mean()),
        "coverage_worst_quarter_of_windows": worst_quarter(windows),
        "coverage_lowest_window": float(windows.min()),
        "pinball_mean": float(pinball_mean(scored, lo, hi).mean()),
        "relative_width": float(((scored[hi] - scored[lo]) / scored["y"]).mean()),
    }


def decide(new: dict[str, float], base: dict[str, float], pinball_ci_low: float) -> dict[str, object]:
    """The pre-registered rule for one calibration against production."""
    checks = {
        "coverage_between_078_and_084": bool(COVERAGE_RANGE[0] <= new["coverage"] <= COVERAGE_RANGE[1]),
        "worst_windows_closer_to_080": bool(
            abs(new["coverage_worst_quarter_of_windows"] - 0.8)
            < abs(base["coverage_worst_quarter_of_windows"] - 0.8)
        ),
        "pinball_not_clearly_worse": bool(not pinball_ci_low > 0),
    }
    return {"checks": checks, "candidate_for_production": all(checks.values())}


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "price"
    name = NAMES[which]
    source = HERE / "results" / f"dense_raw_{which}.json"
    rows = pd.DataFrame(json.loads(source.read_text()))
    rows["origin"], rows["day"] = pd.to_datetime(rows["origin"]), pd.to_datetime(rows["day"])
    buckets = [f"{lo}-{hi}" for lo, hi in TARGETS[name].buckets]
    variants = {label: calibrate_aci(rows, buckets, g) for label, g in GAMMAS.items()}

    # gamma = 0 must be the production calibration, which the file stores as m10 and m90
    base = variants["production"]
    worst = float(
        max(
            ((base["c10"] - base["m10"]) / base["m10"]).abs().max(),
            ((base["c90"] - base["m90"]) / base["m90"]).abs().max(),
        )
    )
    assert worst < 1e-5, f"gamma = 0 differs from production by {worst} (relative)"
    print(f"gamma = 0 reproduces the production band (largest relative difference {worst:.2e})")

    scored_mask = ~base["warmup"].to_numpy()
    out: dict[str, object] = {"target": name, "source": source.name, "gammas": GAMMAS, "variants": {}}
    summaries: dict[str, dict[str, float]] = {}
    for label, frame in variants.items():
        scored = frame[scored_mask].copy()
        scored["m50"] = np.exp(scored["q50_log"])
        scored["origin"] = scored["origin"].astype(str)
        summaries[label] = summarise(scored, "c10", "c90")
        out["variants"][label] = {"origins": int(scored["origin"].nunique()), **summaries[label]}  # type: ignore[index]
    base_scored = base[scored_mask].copy()
    base_scored["m50"] = np.exp(base_scored["q50_log"])
    base_scored["origin"] = base_scored["origin"].astype(str)
    base_loss = pinball_mean(base_scored, "c10", "c90").sort_index()
    out["decision"] = {}
    for label in ("aci_005", "aci_020"):
        scored = variants[label][scored_mask].copy()
        scored["m50"] = np.exp(scored["q50_log"])
        scored["origin"] = scored["origin"].astype(str)
        diff = (pinball_mean(scored, "c10", "c90").sort_index() - base_loss).to_numpy()
        lo, hi = block_bootstrap_ci(diff, BLOCK, draws=5000, seed=7)
        out["variants"][label]["paired_pinball_vs_production"] = {  # type: ignore[index]
            "mean_diff": round(float(diff.mean()), 4),
            "ci95_low": round(lo, 4),
            "ci95_high": round(hi, 4),
        }
        out["decision"][label] = decide(summaries[label], summaries["production"], lo)  # type: ignore[index]
    path = HERE / "results" / f"aci_{which}.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    for label, entry in out["variants"].items():  # type: ignore[attr-defined]
        print(label, json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in entry.items()}))
    print("decision:", json.dumps(out["decision"]))
    print("wrote", path)


if __name__ == "__main__":
    main()
