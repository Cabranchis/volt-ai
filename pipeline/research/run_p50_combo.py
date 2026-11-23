"""A fixed-weight combination of the price forecasts: the model, ETS and "repeat the last price".

Question: does an average of the model's P50 with the other two references have a lower error than
the model alone? Forecast combination is the one idea in the literature that often beats its
components, and "repeat the last price" has never been in a blend here. A blend with ETS whose weight
per horizon bucket was learned online was worse (docs/model-experiments.md, `fb_blend_lgb`, +0.055
with an interval above zero): learned weights add variance. So the weights here are fixed, chosen
before the first run, and there are only two candidates:

    C1  geometric mean of model, ETS and last price, one third each
    C2  geometric mean of model and last price, one half each

(Geometric means, that is averages of logarithms, because the model is trained on the log price.)

Decision rule, written before the first run. A candidate is "a candidate for production" only if:
  (i)  its mean MASE over the whole horizon is lower than the model's, with a paired difference
       (candidate minus model) whose 95 % block-bootstrap interval is entirely below zero, and
  (ii) in none of the buckets 1-3, 4-7 and 8-14 days is it worse than the model with an interval
       entirely above zero.
Otherwise the result is negative, it is recorded as such and production does not change. Nothing else
is read into the result. Whether each candidate belongs to the Model Confidence Set at 4-7 and 8-14
days is reported next to it, not used to decide. The weights are not searched on these dates.

This reads only a saved file (results/dense_backtest.json, 151 dates 7 days apart): no database, no
network. It scores the centre of the forecast only. If a candidate passed, the band would have to be
calibrated again on the blended centre, in a separate step with its own approval.

    uv run python research/run_p50_combo.py

Writes research/results/p50_combo.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from mcs import mcs
from voltia.models.backtest import block_bootstrap_ci

HERE = Path(__file__).parent
SOURCE = HERE / "results" / "dense_backtest.json"
OUT = HERE / "results" / "p50_combo.json"
SLICES = {"all horizons": None, "1-3 days": "1-3", "4-7 days": "4-7", "8-14 days": "8-14"}
BUCKETS = ["1-3 days", "4-7 days", "8-14 days"]
BLOCK = 6  # dates 7 days apart share outcomes over 14 days: the block the other paired intervals use
ALPHA = 0.10
DRAWS = 5000

# column of the dense file for each source, and the fixed weights of each candidate
SOURCES = {"model": "m50", "ets": "ets50", "last_price": "persist"}
CANDIDATES = {
    "C1": {"model": 1 / 3, "ets": 1 / 3, "last_price": 1 / 3},
    "C2": {"model": 1 / 2, "last_price": 1 / 2},
}


def combine(rows: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Weighted geometric mean of the sources' P50. The weights must add up to one."""
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("the weights must add up to one")
    log_sum = sum(w * np.log(rows[SOURCES[name]]) for name, w in weights.items())
    return np.exp(log_sum)


def origin_mase(rows: pd.DataFrame, forecast: pd.Series) -> pd.Series:
    """Mean absolute error over the horizons of each origin, in units of that origin's naive scale."""
    error = (rows["y"] - forecast).abs() / rows["scale"]
    return error.groupby(rows["origin"]).mean()


def losses_for(rows: pd.DataFrame, bucket: str | None) -> pd.DataFrame:
    part = rows if bucket is None else rows[rows["bucket"] == bucket]
    # One filter for every method, so each origin is scored on the same horizons for all of them.
    part = part.dropna(subset=["y", "scale", *SOURCES.values()])
    part = part[(part[list(SOURCES.values())] > 0).all(axis=1)]
    frame = {name: origin_mase(part, part[col]) for name, col in SOURCES.items()}
    for name, weights in CANDIDATES.items():
        frame[name] = origin_mase(part, combine(part, weights))
    return pd.DataFrame(frame).dropna().sort_index()


def paired(losses: pd.DataFrame, name: str) -> dict[str, float]:
    diff = (losses[name] - losses["model"]).to_numpy()
    lo, hi = block_bootstrap_ci(diff, BLOCK, draws=DRAWS, seed=7)
    return {
        "mase": round(float(losses[name].mean()), 4),
        "diff_vs_model": round(float(diff.mean()), 4),
        "ci95_low": round(lo, 4),
        "ci95_high": round(hi, 4),
        "origins_won": int((diff < 0).sum()),
    }


def decide(slices: dict[str, dict[str, dict[str, float]]], name: str) -> dict[str, object]:
    """The pre-registered rule for one candidate, from its paired intervals."""
    whole = slices["all horizons"][name]
    better = whole["diff_vs_model"] < 0 and whole["ci95_high"] < 0
    worse_in = [b for b in BUCKETS if slices[b][name]["ci95_low"] > 0]
    return {
        "i_clearly_better_overall": bool(better),
        "ii_buckets_clearly_worse": worse_in,
        "candidate_for_production": bool(better and not worse_in),
    }


def main() -> None:
    rows = pd.DataFrame(json.loads(SOURCE.read_text()))
    out: dict[str, object] = {
        "source": SOURCE.name,
        "block_length": BLOCK,
        "weights": CANDIDATES,
        "slices": {},
        "mcs": {},
    }
    paired_by_slice: dict[str, dict[str, dict[str, float]]] = {}
    for label, bucket in SLICES.items():
        losses = losses_for(rows, bucket)
        paired_by_slice[label] = {n: paired(losses, n) for n in [*CANDIDATES, "ets", "last_price"]}
        paired_by_slice[label]["model"] = {"mase": round(float(losses["model"].mean()), 4)}
        out["slices"][label] = {"origins": int(len(losses)), "methods": paired_by_slice[label]}  # type: ignore[index]
        result = mcs(losses, alpha=ALPHA, block=BLOCK)
        out["mcs"][label] = {  # type: ignore[index]
            name: {"p_value": round(float(r.p_value), 4), "in_set": bool(r.in_set)} for name, r in result.iterrows()
        }
        print(f"{label:>13} ({len(losses)} origins)")
        for name, m in paired_by_slice[label].items():
            extra = "" if name == "model" else f"  diff {m['diff_vs_model']:+.4f} [{m['ci95_low']:+.4f}, {m['ci95_high']:+.4f}]  won {m['origins_won']}"
            print(f"   {name:<12} MASE {m['mase']:.4f}{extra}")
        print("   in the set:", ", ".join(n for n, r in result.iterrows() if r.in_set))
    out["decision"] = {name: decide(paired_by_slice, name) for name in CANDIDATES}
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("decision:", json.dumps(out["decision"]))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
