"""Conformalised quantile regression (CQR, Romano et al. 2019), asymmetric version.

The lower and upper bounds are shifted separately by an empirical quantile of their past
out-of-sample conformity scores, so each tail aims at its nominal 10 % miss rate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class Offset:
    """Shift of the lower bound (down) and of the upper bound (up), in log units."""

    lower: float = 0.0
    upper: float = 0.0
    n: int = 0


def _conformal_quantile(scores: np.ndarray, alpha: float) -> float:
    """The ceil((n + 1)(1 - alpha))-th smallest score (the largest one if that rank exceeds n)."""
    ordered = np.sort(scores)
    rank = math.ceil((len(ordered) + 1) * (1 - alpha))
    return float(ordered[min(rank, len(ordered)) - 1])


def conformal_offset(
    lower: npt.ArrayLike,
    upper: npt.ArrayLike,
    actual: npt.ArrayLike,
    alpha_lower: float = 0.1,
    alpha_upper: float = 0.1,
) -> Offset:
    """Offsets from past bounds and outcomes, all in the same (log) units."""
    lo = np.asarray(lower, dtype=float)
    hi = np.asarray(upper, dtype=float)
    y = np.asarray(actual, dtype=float)
    ok = ~(np.isnan(lo) | np.isnan(hi) | np.isnan(y))
    if not ok.any():
        return Offset()
    return Offset(
        lower=_conformal_quantile(lo[ok] - y[ok], alpha_lower),
        upper=_conformal_quantile(y[ok] - hi[ok], alpha_upper),
        n=int(ok.sum()),
    )


def apply_offset(q: npt.ArrayLike, offset: Offset) -> np.ndarray:
    """Shift columns 0 and 2 of q (n, 3) outwards and keep p10 <= p50 <= p90."""
    out = np.array(q, dtype=float, copy=True)
    out[:, 0] = np.minimum(out[:, 0] - offset.lower, out[:, 1])
    out[:, 2] = np.maximum(out[:, 2] + offset.upper, out[:, 1])
    return out
