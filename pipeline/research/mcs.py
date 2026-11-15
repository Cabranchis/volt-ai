"""Model Confidence Set (Hansen, Lunde and Nason 2011), the range statistic T_R.

Question it answers: given the per-origin losses of several methods, which of them cannot be told
apart from the best one at level alpha? A paired interval against one reference (what the rest of
this folder reports) says whether A beats B; the MCS says which methods survive when all of them are
compared at once, with the multiple comparisons accounted for.

Procedure: with the methods still in the set, compute for every pair the mean loss difference d_ij
and its bootstrap standard error, t_ij = d_ij / se_ij and T_R = max t_ij (the range statistic, with
its elimination rule: drop the method with the largest max_j t_ij, the one most clearly beaten). The
bootstrap distribution of T_R under equal predictive ability comes from re-centring the resampled
differences. The procedure always runs down to one method. The p-value of a method is the largest
p-value seen up to the round it left, and the last method has p = 1. A method is in the set at
level alpha when its p-value is at least alpha.

The resampling is a circular block bootstrap over origins: consecutive origins share outcomes
(their horizons overlap) and the errors of neighbouring origins are not independent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _block_indices(n: int, block: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    """(n_boot, n) indices of a circular block bootstrap."""
    blocks = -(-n // block)
    starts = rng.integers(0, n, size=(n_boot, blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    return idx.reshape(n_boot, blocks * block)[:, :n]


def _round(losses: np.ndarray, idx: np.ndarray) -> tuple[float, int]:
    """p-value of equal predictive ability for these methods, and the column to drop if rejected."""
    k = losses.shape[1]
    mean = losses.mean(axis=0)
    boot = losses[idx].mean(axis=1)  # (n_boot, k): mean loss of each method in each resample
    d = mean[:, None] - mean[None, :]  # d[i, j]: how much worse i is than j
    d_boot = boot[:, :, None] - boot[:, None, :]
    se = d_boot.std(axis=0, ddof=1)
    off = ~np.eye(k, dtype=bool)
    usable = off & (se > 0)
    t = np.zeros((k, k))
    t[usable] = d[usable] / se[usable]
    # A difference that never moves across resamples is as clear as a difference can be.
    t[off & (se == 0) & (d != 0)] = np.sign(d[off & (se == 0) & (d != 0)]) * np.inf
    observed = t.max()
    centred = np.zeros_like(d_boot)
    centred[:, usable] = (d_boot[:, usable] - d[usable]) / se[usable]
    simulated = centred.reshape(len(idx), -1).max(axis=1)
    p = float((simulated >= observed).mean())
    return p, int(t.max(axis=1).argmax())


def mcs(
    losses: pd.DataFrame,
    alpha: float = 0.10,
    n_boot: int = 5000,
    block: int = 4,
    seed: int = 7,
) -> pd.DataFrame:
    """Rows: methods. Columns: mean_loss, p_value, in_set (p_value >= alpha). Sorted by p_value.

    `losses` has one row per origin and one column per method (lower is better, no missing values).
    """
    if losses.shape[1] < 2:
        raise ValueError("a confidence set needs at least two methods")
    if losses.isna().any().any():
        raise ValueError("losses must be complete: drop or fill the origins a method did not score")
    n = len(losses)
    if n < 8:
        raise ValueError("too few origins for a block bootstrap")
    rng = np.random.default_rng(seed)
    idx = _block_indices(n, block, n_boot, rng)
    values = losses.to_numpy(dtype=float)
    names = list(losses.columns)
    alive = list(range(len(names)))
    p_value: dict[str, float] = {}
    running = 0.0
    while len(alive) > 1:
        p, worst = _round(values[:, alive], idx)
        running = max(running, p)
        p_value[names[alive.pop(worst)]] = running
    p_value[names[alive[0]]] = 1.0
    out = pd.DataFrame(
        {
            "mean_loss": losses.mean(),
            "p_value": pd.Series(p_value),
        }
    )
    out["in_set"] = out["p_value"] >= alpha
    return out.sort_values("p_value", ascending=False)
