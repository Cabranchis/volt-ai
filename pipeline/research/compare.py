"""Paired comparison of two experiments' per-row forecasts on the same origins.

Usage: python compare.py <candidate> <reference> [more references...]
Negative differences favour the candidate. Reads data/rows_<name>.csv written by run_price.py.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import harness


def per_origin_mase(name: str) -> pd.Series:
    rows = pd.read_csv(harness.DATA / f"rows_{name}.csv", parse_dates=["origin", "day"])
    return harness.per_origin(rows, "m", "mase")


def compare(candidate: str, reference: str, draws: int = 4000, seed: int = 7) -> dict[str, float]:
    a, b = per_origin_mase(candidate), per_origin_mase(reference)
    diff = (a - b).dropna().to_numpy()
    rng = np.random.default_rng(seed)
    means = rng.choice(diff, size=(draws, len(diff)), replace=True).mean(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    return {
        "candidate": float(a.mean()),
        "reference": float(b.mean()),
        "diff": float(diff.mean()),
        "lo": float(lo),
        "hi": float(hi),
        "wins": int((diff < 0).sum()),
        "origins": len(diff),
    }


if __name__ == "__main__":
    for ref in sys.argv[2:]:
        r = compare(sys.argv[1], ref)
        print(
            f"{sys.argv[1]} vs {ref}: MASE {r['candidate']:.3f} vs {r['reference']:.3f}  diff {r['diff']:+.3f} "
            f"[{r['lo']:+.3f}, {r['hi']:+.3f}]  wins {r['wins']}/{r['origins']}"
        )
