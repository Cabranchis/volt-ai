"""Baselines reported next to the model: seasonal naive and ETS (requirement FR-07)."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.exponential_smoothing.ets import ETSModel

from voltia.features import complete_daily

SEASON = 7


def _series_to(y: pd.Series, origin: pd.Timestamp) -> pd.Series:
    frame = complete_daily(y.to_frame("y"))["y"]
    seen = frame.loc[: pd.Timestamp(origin).as_unit("ns")]
    if seen.empty or seen.index[-1] != pd.Timestamp(origin) or np.isnan(seen.iloc[-1]):
        raise ValueError(f"no observation at the origin {pd.Timestamp(origin).date()}")
    return seen


def seasonal_naive(y: pd.Series, origin: pd.Timestamp, horizon: int) -> np.ndarray:
    """Same weekday of the last observed week, repeated for horizons beyond 7.

    A missing reference day falls back to the same weekday one week earlier.
    """
    values = _series_to(y, origin).to_numpy(dtype=float)
    out = np.full(horizon, np.nan)
    for h in range(1, horizon + 1):
        for back in range((-h) % SEASON, min(len(values), 5 * SEASON), SEASON):
            value = values[len(values) - 1 - back]
            if not np.isnan(value):
                out[h - 1] = value
                break
    return out


def seasonal_naive_quantiles(
    y: pd.Series,
    origin: pd.Timestamp,
    horizon: int,
    window_days: int = 728,
    quantiles: tuple[float, float] = (0.1, 0.9),
) -> np.ndarray:
    """Seasonal naive with intervals from its own past h-step log errors.

    Errors come from forecast origins t in the last `window_days` with t + h <= origin, so
    only observed outcomes are used. Returns an array (horizon, 3): lower, point, upper.
    """
    seen = _series_to(y, origin)
    logy = pd.Series(np.log(seen.where(seen > 0)), index=seen.index)
    point = seasonal_naive(y, origin, horizon)
    out = np.empty((horizon, 3))
    for h in range(1, horizon + 1):
        err = (logy.shift(-h) - logy.shift((-h) % SEASON)).iloc[:-h].iloc[-window_days:]
        err = err.dropna()
        if len(err) < 30:
            raise ValueError("not enough history for seasonal naive intervals")
        lo, hi = np.quantile(err.to_numpy(), quantiles)
        out[h - 1] = [point[h - 1] * np.exp(lo), point[h - 1], point[h - 1] * np.exp(hi)]
    out[:, 0] = np.minimum(out[:, 0], out[:, 1])
    out[:, 2] = np.maximum(out[:, 2], out[:, 1])
    return out


def ets_forecast(
    y: pd.Series,
    origin: pd.Timestamp,
    horizon: int,
    log: bool,
    window_days: int = 1092,
    alpha: float = 0.2,
) -> np.ndarray:
    """ETS(A,Ad,A) with weekly seasonality, fitted on the last `window_days` up to the origin.

    With log=True the model is fitted on log values and transformed back, so the point
    forecast is a median. Returns an array (horizon, 3): lower, point, upper.
    """
    seen = _series_to(y, origin).iloc[-window_days:]
    values = seen.interpolate(limit_direction="both").astype(float)
    if log:
        values = pd.Series(np.log(values), index=values.index)
    model = ETSModel(
        values,
        error="add",
        trend="add",
        damped_trend=True,
        seasonal="add",
        seasonal_periods=SEASON,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fitted = model.fit(disp=False, maxiter=200)
        prediction = fitted.get_prediction(start=len(values), end=len(values) + horizon - 1)
        summary = prediction.summary_frame(alpha=alpha)
    out = summary[["pi_lower", "mean", "pi_upper"]].to_numpy(dtype=float)
    if log:
        out = np.exp(out)
    return np.asarray(np.maximum(np.sort(out, axis=1), 0.0), dtype=float)
