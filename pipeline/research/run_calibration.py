"""Does a band calibrated for the current regime cover better in stress? (development origins)

The price model's P10-P90 band is shifted by conformal offsets learned from past scores
(`voltia.models.backtest.calibrate_online`), every past origin with the same weight. In stress the
band covered 68-71 % of days against the 80 % it promises. This script compares four calibrations on
the saved development rows (raw quantiles of `fs1_xgb`; nothing is retrained):

  V0  the current one (every past origin, equal weight)
  V1  recency weights (half-life HALF_LIFE origins)
  V2  scores divided by the recent price volatility at their origin, rescaled by today's
  V3  only past origins in the same regime (stress or not), V0 when fewer than MIN_ORIGINS

Decision rule, written before the first run (docs/model-experiments.md and STATE.md): a variant wins
if (a) coverage in the most volatile third of origins is at least 0.70 and closer to 0.80 than V0,
(b) overall coverage is 0.80 +- 0.05, (c) mean relative width is at most 15 % above V0, and (d) its
mean pinball is not worse than V0 (paired bootstrap over origins in blocks of 3).
Stress: volatility above the 75th percentile of the development origins, or thermal share of
generation (7 days) above 30 %, or reservoir level below 40 %.

    cd pipeline && uv run python research/run_calibration.py [dev|reported <variant>]
"""

from __future__ import annotations

import math
import sys

import numpy as np
import pandas as pd
from harness import DATA, SETTLE_LAG, load_data
from voltia.features import TARGETS
from voltia.models import metrics
from voltia.models.backtest import calibrate_online
from voltia.models.calibration import Offset, apply_offset, conformal_offset

SPEC = TARGETS["price_mean_cop_kwh"]
MIN_ORIGINS = 4
HALF_LIFE = 6.0
VOL_WINDOW = 28
VOL_FLOOR = 0.03
STRESS_THERMAL = 0.30
STRESS_RESERVOIR = 0.40
ALPHA = 0.1
VARIANTS = ("V0", "V1", "V2", "V3")


def origin_state(origins: list[pd.Timestamp]) -> pd.DataFrame:
    """Volatility, thermal share and reservoir level known on each origin (nothing newer)."""
    data = load_data()
    logp = np.log(data["price_mean_cop_kwh"])
    thermal = (data["gen_thermal_kwh"] / data["gen_total_kwh"]).rolling(7, min_periods=4).mean()
    rows = []
    for o in origins:
        known = o - pd.Timedelta(days=SETTLE_LAG)
        window = logp.loc[known - pd.Timedelta(days=VOL_WINDOW) : known].diff().dropna()
        rows.append(
            {
                "origin": o,
                "vol": max(float(window.std()), VOL_FLOOR) if len(window) > 5 else np.nan,
                "thermal": float(thermal.loc[:known].dropna().iloc[-1]),
                "reservoir": float(data["reservoir_pct"].loc[: o - pd.Timedelta(days=1)].dropna().iloc[-1]),
            }
        )
    return pd.DataFrame(rows).set_index("origin")


def weighted_quantile(scores: np.ndarray, weights: np.ndarray, alpha: float) -> float:
    """Conformal quantile with weights; the test point carries weight 1 at +infinity."""
    order = np.argsort(scores)
    s, w = scores[order], weights[order]
    cum = np.cumsum(w) / (w.sum() + 1.0)
    hit = np.flatnonzero(cum >= 1 - alpha)
    return float(s[hit[0]] if len(hit) else s[-1])


def offsets_for(past: pd.DataFrame, here: pd.Timestamp, state: pd.DataFrame, variant: str) -> Offset:
    """Offset (log units) for the rows of one origin and one horizon bucket."""
    y = np.log(past["y"].to_numpy())
    lo = past["q10_log"].to_numpy() - y
    hi = y - past["q90_log"].to_numpy()
    origins = past["origin"].to_numpy()
    if variant == "V0":
        return conformal_offset(past["q10_log"], past["q90_log"], y)
    if variant == "V1":
        ordered = sorted(set(origins))
        age = {o: len(ordered) - 1 - i for i, o in enumerate(ordered)}
        w = np.array([0.5 ** (age[o] / HALF_LIFE) for o in origins])
        return Offset(weighted_quantile(lo, w, ALPHA), weighted_quantile(hi, w, ALPHA), len(y))
    if variant == "V2":
        vol_past = state.loc[pd.DatetimeIndex(origins), "vol"].to_numpy()
        vol_now = float(state.loc[here, "vol"])
        w = np.ones(len(y))
        return Offset(
            weighted_quantile(lo / vol_past, w, ALPHA) * vol_now,
            weighted_quantile(hi / vol_past, w, ALPHA) * vol_now,
            len(y),
        )
    if variant == "V3":
        flag_past = state.loc[pd.DatetimeIndex(origins), "stress"].to_numpy()
        same = flag_past == bool(state.loc[here, "stress"])
        if len({o for o, s in zip(origins, same, strict=True) if s}) < MIN_ORIGINS:
            return conformal_offset(past["q10_log"], past["q90_log"], y)
        return conformal_offset(past["q10_log"][same], past["q90_log"][same], y[same])
    raise ValueError(variant)


def calibrate(rows: pd.DataFrame, state: pd.DataFrame, variant: str) -> pd.DataFrame:
    """Same contract as `calibrate_online`: m10/m50/m90 from outcomes seen before each origin."""
    out = rows.copy()
    for name in ("m10", "m50", "m90"):
        out[name] = np.nan
    out["calibrated"] = False
    for origin in sorted(out["origin"].unique()):
        here = out["origin"] == origin
        past = out[(out["origin"] < origin) & (out["day"] <= origin) & out["y"].notna()]
        enough = past["origin"].nunique() >= MIN_ORIGINS
        for label in out.loc[here, "bucket"].unique():
            sel = here & (out["bucket"] == label)
            q = out.loc[sel, ["q10_log", "q50_log", "q90_log"]].to_numpy()
            offset = Offset()
            if enough:
                offset = offsets_for(past[past["bucket"] == label], origin, state, variant)
            out.loc[sel, ["m10", "m50", "m90"]] = np.exp(apply_offset(q, offset))
        out.loc[here, "calibrated"] = enough
    return out


def scored(rows: pd.DataFrame) -> pd.DataFrame:
    return rows[(~rows["warmup"]) & rows["calibrated"] & rows["y"].notna()]


def per_origin(rows: pd.DataFrame) -> pd.DataFrame:
    def one(p: pd.DataFrame) -> pd.Series:
        y = p["y"].to_numpy()
        lo, mid, hi = (p[c].to_numpy() for c in ("m10", "m50", "m90"))
        pin = np.mean([metrics.pinball(y, q, a) for q, a in zip((lo, mid, hi), (0.1, 0.5, 0.9), strict=True)])
        return pd.Series(
            {
                "coverage": metrics.coverage(y, lo, hi),
                "width": float(np.mean((hi - lo) / mid)),
                "pinball": float(pin),
            }
        )

    return scored(rows).groupby("origin").apply(one)


def paired_ci(diff: np.ndarray, block: int = 3, n_boot: int = 4000, seed: int = 7) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(diff)
    starts = np.arange(0, n - block + 1)
    reps = math.ceil(n / block)
    means = []
    for _ in range(n_boot):
        pick = rng.choice(starts, reps)
        sample = np.concatenate([diff[s : s + block] for s in pick])[:n]
        means.append(sample.mean())
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "dev"
    if mode == "reported":
        # One run only, of the winner named on the command line (docs/model-experiments.md).
        variants = [sys.argv[2]]
        file = "rows_reported_fs1_xgb.csv"
    else:
        variants = list(VARIANTS)
        file = "rows_fs1_xgb.csv"
    rows = pd.read_csv(DATA / file, parse_dates=["origin", "day"])
    state = origin_state(sorted(rows["origin"].unique()))
    dev_vol = state.loc[state.index <= pd.Timestamp("2023-10-12"), "vol"]
    cut = float(dev_vol.quantile(0.75))
    state["stress"] = (state["vol"] > cut) | (state["thermal"] > STRESS_THERMAL) | (state["reservoir"] < STRESS_RESERVOIR)
    print(f"{file}: {rows['origin'].nunique()} origins; volatility p75 of development = {cut:.4f}")
    print(f"origins flagged stress: {int(state['stress'].sum())} of {len(state)}")

    # V0 here must be the production calibration.
    ref = calibrate_online(rows, MIN_ORIGINS, SPEC)
    mine = calibrate(rows, state, "V0")
    assert np.allclose(ref[["m10", "m50", "m90"]], mine[["m10", "m50", "m90"]], equal_nan=True), "V0 differs"

    results = {v: per_origin(calibrate(rows, state, v)) for v in variants}
    top = state["vol"].rank(pct=True) > 2 / 3
    base = results.get("V0")
    print("\nvariant | coverage all | coverage volatile third | coverage rest | width | pinball | pinball diff vs V0 [95 %]")
    for v, res in results.items():
        vol_third = res.index.isin(state.index[top])
        d = ""
        if base is not None and v != "V0":
            lo, hi = paired_ci((res["pinball"] - base["pinball"]).to_numpy())
            d = f"{(res['pinball'] - base['pinball']).mean():+.3f} [{lo:+.3f}, {hi:+.3f}]"
        print(
            f"{v} | {res['coverage'].mean():.3f} | {res.loc[vol_third, 'coverage'].mean():.3f} | "
            f"{res.loc[~vol_third, 'coverage'].mean():.3f} | {res['width'].mean():.3f} | {res['pinball'].mean():.3f} | {d}"
        )
    print(f"\norigins scored: {len(next(iter(results.values())))}; volatile third: {int(top.sum())} origins")


if __name__ == "__main__":
    main()
