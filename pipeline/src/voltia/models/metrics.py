"""Point and probabilistic forecast metrics. Inputs are 1-D arrays of equal length."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pandas as pd

Array = npt.ArrayLike


def _pair(y: Array, yhat: Array) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(y, dtype=float)
    b = np.asarray(yhat, dtype=float)
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch: {a.shape} vs {b.shape}")
    return a, b


def mape(y: Array, yhat: Array) -> float:
    """Mean absolute percentage error, in percent."""
    a, b = _pair(y, yhat)
    return float(np.mean(np.abs(a - b) / np.abs(a)) * 100)


def smape(y: Array, yhat: Array) -> float:
    """Symmetric MAPE, in percent (0..200)."""
    a, b = _pair(y, yhat)
    return float(np.mean(2 * np.abs(a - b) / (np.abs(a) + np.abs(b))) * 100)


def mase(y: Array, yhat: Array, scale: Array) -> float:
    """Mean absolute error divided by a scale (a scalar or one value per row)."""
    a, b = _pair(y, yhat)
    s = np.broadcast_to(np.asarray(scale, dtype=float), a.shape)
    return float(np.mean(np.abs(a - b) / s))


def mase_scale(history: pd.Series, m: int = 7) -> float:
    """In-sample MAE of the seasonal naive forecast with period m (calendar days)."""
    values = history.astype(float)
    diff = (values - values.shift(m)).abs().dropna()
    if diff.empty:
        raise ValueError("not enough history to compute the MASE scale")
    return float(diff.mean())


def pinball(y: Array, q: Array, alpha: float) -> float:
    """Mean pinball (quantile) loss of the alpha-quantile forecast q."""
    a, b = _pair(y, q)
    diff = a - b
    return float(np.mean(np.maximum(alpha * diff, (alpha - 1) * diff)))


def coverage(y: Array, lower: Array, upper: Array) -> float:
    """Share of observations inside [lower, upper]."""
    a, lo = _pair(y, lower)
    _, hi = _pair(y, upper)
    return float(np.mean((a >= lo) & (a <= hi)))
