"""Anomaly detection on demand and price (requirement FR-09).

1. Robust STL on log values with a weekly period. The 13-week trend window keeps slow,
   seasonal-scale moves in the trend, while events lasting days to a few weeks stay in the
   residual.
2. Calendar adjustment: a Huber regression of the residual on holiday flags (weekday
   holidays, long-weekend Saturdays and Sundays, Holy Week, the year-end season, and Dec 24,
   25, 31 and Jan 1), so an ordinary public holiday is not reported as atypical.
3. Robust z-score of the adjusted residual (median and MAD).
4. Isolation Forest on a small vector per day: the z-score, its centred 7-day mean (sustained
   shifts) and its day-to-day change (abrupt jumps), each robust-scaled.
5. Severity = mean of |z| and the robust z of the Isolation Forest score (floored at 0).
   A day is flagged when its severity reaches the (1 - target_rate) quantile (and at least
   min_severity) and its own |z| is at least min_abs_z, so pure noise is rarely flagged.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import HuberRegressor
from statsmodels.tsa.seasonal import STL

from voltia.features import calendar_frame, complete_daily

METHOD = "stl_robust_z+isolation_forest"


def _calendar_regressors(start: pd.Timestamp, end: pd.Timestamp) -> np.ndarray:
    """Holiday effects on top of the weekly cycle: a Sunday holiday changes little."""
    cal = calendar_frame(start, end)
    weekday = (cal["dow"] < 5).astype(float)
    return np.column_stack(
        [
            cal["is_holiday"] * weekday,
            cal["in_long_weekend"] * (1 - weekday),
            cal["holy_week"] * weekday,
            cal["year_end"],
            cal["christmas_new_year"],
        ]
    )


@dataclass(frozen=True)
class AnomalyConfig:
    period: int = 7
    seasonal: int = 13
    trend: int = 91
    target_rate: float = 0.02
    min_severity: float = 3.0
    min_abs_z: float = 3.5
    n_estimators: int = 200
    seed: int = 20261024


def _robust_z(values: np.ndarray) -> np.ndarray:
    median = np.nanmedian(values)
    mad = np.nanmedian(np.abs(values - median)) * 1.4826
    return np.asarray((values - median) / (mad if mad > 0 else 1.0), dtype=float)


def score_series(series: pd.Series, cfg: AnomalyConfig | None = None) -> pd.DataFrame:
    """Score every observed day of a positive daily series. Returns one row per day."""
    cfg = cfg or AnomalyConfig()
    full = complete_daily(series.to_frame("y"))["y"]
    full = full.loc[full.first_valid_index() : full.last_valid_index()]
    observed = full.notna() & (full > 0)
    logy = np.log(full.where(observed)).interpolate(limit_direction="both")

    stl = STL(logy, period=cfg.period, seasonal=cfg.seasonal, trend=cfg.trend, robust=True)
    resid = stl.fit().resid.to_numpy()

    cal = _calendar_regressors(full.index[0], full.index[-1])
    huber = HuberRegressor(max_iter=500).fit(cal[observed.to_numpy()], resid[observed.to_numpy()])
    adjusted = resid - (cal @ huber.coef_)
    adjusted[~observed.to_numpy()] = np.nan

    z = _robust_z(adjusted)
    z_series = pd.Series(z, index=full.index)
    sustained = z_series.rolling(7, center=True, min_periods=4).mean().to_numpy()
    jump = z_series.diff().to_numpy()
    vector = np.column_stack([z, _robust_z(sustained), _robust_z(jump)])
    vector = np.nan_to_num(vector, nan=0.0)
    forest = IsolationForest(n_estimators=cfg.n_estimators, random_state=cfg.seed)
    forest.fit(vector[observed.to_numpy()])
    iso = _robust_z(-forest.score_samples(vector))

    severity = (np.abs(z) + np.maximum(iso, 0.0)) / 2
    severity[~observed.to_numpy()] = np.nan
    expected = np.exp(logy.to_numpy() - (adjusted - np.nanmedian(adjusted)))
    return pd.DataFrame(
        {
            "day": full.index,
            "observed": full.to_numpy(),
            "expected": expected,
            "z": z,
            "iforest_z": iso,
            "severity": severity,
        }
    )


def detect(series: pd.Series, target: str, cfg: AnomalyConfig | None = None) -> pd.DataFrame:
    """Flagged days for one target, in the layout of the `anomalies` table."""
    cfg = cfg or AnomalyConfig()
    scored = score_series(series, cfg).dropna(subset=["severity"])
    threshold = max(cfg.min_severity, float(np.quantile(scored["severity"], 1 - cfg.target_rate)))
    flagged = scored[(scored["severity"] >= threshold) & (scored["z"].abs() >= cfg.min_abs_z)]
    details = [
        {
            "z": round(float(z), 2),
            "iforest_z": round(float(iso), 2),
            "observed": round(float(obs), 2),
            "expected": round(float(exp), 2),
            "deviation_pct": round(float((obs / exp - 1) * 100), 1),
            "threshold": round(threshold, 2),
        }
        for z, iso, obs, exp in zip(
            flagged["z"].to_numpy(dtype=float),
            flagged["iforest_z"].to_numpy(dtype=float),
            flagged["observed"].to_numpy(dtype=float),
            flagged["expected"].to_numpy(dtype=float),
            strict=True,
        )
    ]
    return pd.DataFrame(
        {
            "target": target,
            "day": flagged["day"].to_numpy(),
            "severity": flagged["severity"].round(3).to_numpy(),
            "direction": np.where(flagged["z"] > 0, "high", "low"),
            "method": METHOD,
            "detail": details,
        }
    )


def detect_all(
    history: pd.DataFrame, targets: tuple[str, ...], cfg: AnomalyConfig | None = None
) -> pd.DataFrame:
    frames = [detect(history[t].dropna(), t, cfg) for t in targets]
    return pd.concat(frames, ignore_index=True)
