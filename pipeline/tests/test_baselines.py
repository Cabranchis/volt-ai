from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from voltia.models.baselines import ets_forecast, seasonal_naive, seasonal_naive_quantiles


def _series(values: list[float], start: str = "2024-01-01") -> pd.Series:
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"))


def test_seasonal_naive_repeats_the_last_week() -> None:
    # 14 days, values 1..14; origin is the last day (value 14).
    y = _series([float(v) for v in range(1, 15)])
    forecast = seasonal_naive(y, y.index[-1], 10)
    # h=1 -> same weekday last week = day 8; h=7 -> day 14; h=8 -> day 8 again.
    assert forecast.tolist() == [8, 9, 10, 11, 12, 13, 14, 8, 9, 10]


def test_seasonal_naive_falls_back_one_week_when_the_reference_is_missing() -> None:
    values = [float(v) for v in range(1, 15)]
    values[7] = np.nan  # day 8, the reference for h=1
    y = _series(values)
    assert seasonal_naive(y, y.index[-1], 1).tolist() == [1.0]


def test_seasonal_naive_needs_an_observation_at_the_origin() -> None:
    y = _series([1.0, 2.0, np.nan])
    with pytest.raises(ValueError, match="no observation"):
        seasonal_naive(y, y.index[-1], 3)


def test_seasonal_naive_intervals_are_empty_for_a_perfect_weekly_pattern() -> None:
    pattern = [10.0, 11, 12, 13, 14, 8, 6]
    y = _series(pattern * 20)
    out = seasonal_naive_quantiles(y, y.index[-1], 9)
    assert np.allclose(out[:, 0], out[:, 1])
    assert np.allclose(out[:, 2], out[:, 1])
    assert np.allclose(out[:7, 1], pattern)


def test_seasonal_naive_intervals_use_only_the_past() -> None:
    rng = np.random.default_rng(0)
    y = _series(list(100 * np.exp(rng.normal(0, 0.05, 200))))
    origin = y.index[150]
    before = seasonal_naive_quantiles(y, origin, 5)
    y.iloc[151:] = 1e6
    assert np.array_equal(before, seasonal_naive_quantiles(y, origin, 5))
    assert (before[:, 0] <= before[:, 1]).all()
    assert (before[:, 1] <= before[:, 2]).all()


@pytest.mark.parametrize("log", [False, True])
def test_ets_tracks_a_weekly_pattern_with_ordered_bounds(log: bool) -> None:
    rng = np.random.default_rng(3)
    pattern = np.array([100.0, 104, 106, 105, 103, 90, 80])
    days = 400
    values = np.tile(pattern, days // 7 + 1)[:days] * np.exp(rng.normal(0, 0.01, days))
    y = _series(list(values))
    out = ets_forecast(y, y.index[-1], 14, log=log)
    truth = np.tile(pattern, 4)[days % 7 : days % 7 + 14]
    assert out.shape == (14, 3)
    assert np.all(out[:, 0] <= out[:, 1])
    assert np.all(out[:, 1] <= out[:, 2])
    assert np.mean(np.abs(out[:, 1] / truth - 1)) < 0.03
