"""Model Confidence Set over the methods of the dense price backtest.

The dense backtest (run_dense_backtest.py, 151 test dates 7 days apart) is the only result file that
keeps the loss of every method on every origin: the model, ETS, the weekly seasonal naive and
"repeat the last price". The per-candidate files of the model experiments keep only averages, so the
50 candidates of docs/model-experiments.md cannot be put in a set without running them again.

Decision rule, written before the first run: the production model is "supported" if it belongs to
the set at alpha = 0.10 for the mean MASE of the whole horizon; it is "not distinguishable from X" for
every other method X that is in the set with it. Nothing else is read into the result.

    uv run python research/run_mcs.py

Writes research/results/mcs_dense_backtest.json. It reads only a saved file: no database, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from mcs import mcs

HERE = Path(__file__).parent
SOURCE = HERE / "results" / "dense_backtest.json"
OUT = HERE / "results" / "mcs_dense_backtest.json"
METHODS = {"model": "m50", "ets": "ets50", "seasonal_naive": "sn50", "last_price": "persist"}
SLICES = {"all horizons": None, "1-3 days": "1-3", "4-7 days": "4-7", "8-14 days": "8-14"}
ALPHA = 0.10
BLOCK = 6  # dates 7 days apart share outcomes over 14 days: the same block the paired intervals use


def origin_mase(rows: pd.DataFrame, column: str) -> pd.Series:
    """Mean absolute error over the horizons of each origin, in units of that origin's naive scale."""
    scored = rows[rows["y"].notna() & rows[column].notna()]
    error = (scored["y"] - scored[column]).abs() / scored["scale"]
    return error.groupby(scored["origin"]).mean()


def losses_for(rows: pd.DataFrame, bucket: str | None) -> pd.DataFrame:
    part = rows if bucket is None else rows[rows["bucket"] == bucket]
    # One filter for every method, so each origin is scored on the same horizons for all of them.
    part = part.dropna(subset=["y", "scale", *METHODS.values()])
    frame = pd.DataFrame({name: origin_mase(part, col) for name, col in METHODS.items()})
    return frame.dropna().sort_index()


def main() -> None:
    rows = pd.DataFrame(json.loads(SOURCE.read_text()))
    out: dict[str, object] = {"alpha": ALPHA, "source": SOURCE.name, "block_length": BLOCK, "slices": {}}
    for label, bucket in SLICES.items():
        losses = losses_for(rows, bucket)
        result = mcs(losses, alpha=ALPHA, block=BLOCK)
        out["slices"][label] = {  # type: ignore[index]
            "origins": int(len(losses)),
            "methods": {
                name: {
                    "mase": round(float(r.mean_loss), 4),
                    "p_value": round(float(r.p_value), 4),
                    "in_set": bool(r.in_set),
                }
                for name, r in result.iterrows()
            },
        }
        kept = [n for n, r in result.iterrows() if r.in_set]
        print(f"{label:>13} ({len(losses)} origins): in the set -> {', '.join(kept)}")
        print(result.round(4).to_string())
        print()
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
    assert np.isfinite(sum(m["mase"] for s in out["slices"].values() for m in s["methods"].values()))  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
