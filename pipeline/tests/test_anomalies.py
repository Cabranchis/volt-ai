from __future__ import annotations

import numpy as np
import pandas as pd

from voltia.anomalies import METHOD, AnomalyConfig, detect, detect_all, score_series


def _noise(days: int = 730, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2023-01-01", periods=days, freq="D")
    weekly = np.array([1.0, 1.01, 1.01, 1.01, 1.0, 0.93, 0.86])[index.day_of_week]
    return pd.Series(2e8 * weekly * np.exp(rng.normal(0, 0.01, days)), index=index)


def test_an_injected_spike_is_flagged_high() -> None:
    series = _noise()
    spike_day = pd.Timestamp("2024-03-13")  # a Wednesday, not a holiday
    series[spike_day] *= 1.25
    out = detect(series, "demand_kwh")
    assert spike_day in set(pd.DatetimeIndex(out["day"]))
    row = out[pd.DatetimeIndex(out["day"]) == spike_day].iloc[0]
    assert row["direction"] == "high"
    assert row["severity"] == out["severity"].max()
    assert row["method"] == METHOD
    assert row["detail"]["deviation_pct"] > 15


def test_a_low_dip_is_flagged_low() -> None:
    series = _noise(seed=1)
    dip = pd.Timestamp("2024-09-18")
    series[dip] *= 0.8
    out = detect(series, "demand_kwh")
    row = out[pd.DatetimeIndex(out["day"]) == dip]
    assert len(row) == 1
    assert row.iloc[0]["direction"] == "low"


def test_pure_noise_raises_few_flags() -> None:
    series = _noise(seed=2)
    out = detect(series, "demand_kwh")
    assert len(out) <= 0.01 * len(series)
    assert (out["severity"] >= 0).all()


def test_scores_are_deterministic_and_skip_missing_days() -> None:
    series = _noise(seed=3)
    series.iloc[100] = np.nan
    a = score_series(series, AnomalyConfig())
    b = score_series(series, AnomalyConfig())
    pd.testing.assert_frame_equal(a, b)
    assert np.isnan(a.loc[100, "severity"])


def test_detect_all_combines_targets(history: pd.DataFrame) -> None:
    out = detect_all(history, ("demand_kwh", "price_mean_cop_kwh"))
    assert set(out["target"]) <= {"demand_kwh", "price_mean_cop_kwh"}
    assert set(out["direction"]) <= {"high", "low"}
    assert len(out) <= 0.03 * 2 * len(history)
