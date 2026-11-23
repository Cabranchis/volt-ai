from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from run_aci import calibrate_aci, decide, window_coverage, worst_quarter
from voltia.features import TARGETS
from voltia.models.backtest import calibrate_online

SPEC = TARGETS["price_mean_cop_kwh"]
BUCKETS = [f"{lo}-{hi}" for lo, hi in SPEC.buckets]


def _bucket(h: int) -> str:
    return next(f"{lo}-{hi}" for lo, hi in SPEC.buckets if lo <= h <= hi)


def _rows(n_origins: int = 40, shock_from: int | None = None, seed: int = 0) -> pd.DataFrame:
    """Weekly origins, horizons 1..14, a raw band of +-0.1 in logs around a flat price of 300."""
    rng = np.random.default_rng(seed)
    records = []
    for o in range(n_origins):
        origin = pd.Timestamp("2025-01-01") + pd.Timedelta(days=7 * o)
        for h in range(1, 15):
            noise = rng.normal(0, 0.08)
            if shock_from is not None and o >= shock_from:
                noise += 0.25  # the price runs above the band
            records.append(
                {
                    "origin": origin,
                    "day": origin + pd.Timedelta(days=h),
                    "h": h,
                    "bucket": _bucket(h),
                    "y": float(300 * np.exp(noise)),
                    "q10_log": float(np.log(300) - 0.1),
                    "q50_log": float(np.log(300)),
                    "q90_log": float(np.log(300) + 0.1),
                }
            )
    return pd.DataFrame(records)


def test_gamma_zero_is_the_production_calibration() -> None:
    rows = _rows()
    production = calibrate_online(rows, 4, SPEC).sort_values(["origin", "h"]).reset_index(drop=True)
    aci = calibrate_aci(rows, BUCKETS, gamma=0.0)
    np.testing.assert_allclose(aci["c10"], production["m10"], rtol=1e-12)
    np.testing.assert_allclose(aci["c90"], production["m90"], rtol=1e-12)
    assert (aci["calibrated"].to_numpy() == production["calibrated"].to_numpy()).all()


def test_misses_above_the_band_widen_the_upper_side_only() -> None:
    rows = _rows(shock_from=15)
    base = calibrate_aci(rows, BUCKETS, gamma=0.0)
    aci = calibrate_aci(rows, BUCKETS, gamma=0.02)
    late = aci["origin"] >= pd.Timestamp("2025-01-01") + pd.Timedelta(days=7 * 25)
    assert (aci.loc[late, "c90"] >= base.loc[late, "c90"] - 1e-9).all()
    assert (aci.loc[late, "c90"] > base.loc[late, "c90"] + 1e-6).any()
    # the lower side saw no misses, so its level only drifts down to a narrower side: never wider
    assert (aci.loc[late, "c10"] >= base.loc[late, "c10"] - 1e-9).all()


def test_the_band_at_an_origin_does_not_depend_on_later_outcomes() -> None:
    rows = _rows()
    origin = pd.Timestamp("2025-01-01") + pd.Timedelta(days=7 * 20)
    base = calibrate_aci(rows, BUCKETS, gamma=0.02)
    changed = rows.copy()
    later = (changed["day"] > origin)
    changed.loc[later, "y"] = changed.loc[later, "y"] * 3.0  # every outcome after the origin day
    again = calibrate_aci(changed, BUCKETS, gamma=0.02)
    here = base["origin"] == origin
    pd.testing.assert_series_equal(base.loc[here, "c10"], again.loc[here, "c10"])
    pd.testing.assert_series_equal(base.loc[here, "c90"], again.loc[here, "c90"])


def test_a_day_updates_the_level_once_and_only_after_it_is_known() -> None:
    rows = _rows(n_origins=12, shock_from=5)
    aci = calibrate_aci(rows, BUCKETS, gamma=0.02)
    # the first calibrated origin is the fifth; its band equals production's, nothing was fed back yet
    base = calibrate_aci(rows, BUCKETS, gamma=0.0)
    first = sorted(rows["origin"].unique())[4]
    here = aci["origin"] == first
    pd.testing.assert_series_equal(aci.loc[here, "c90"], base.loc[here, "c90"])


def test_window_coverage_and_worst_quarter() -> None:
    inside = pd.Series([True, True, False, False, True, True, True, True, True, True])
    origins = pd.Series(range(10))
    windows = window_coverage(inside, origins, window=4)
    assert len(windows) == 7
    assert windows.min() == pytest.approx(0.5)
    assert worst_quarter(windows) == pytest.approx(windows.sort_values().iloc[:2].mean())


def test_the_rule_needs_all_three_checks() -> None:
    good = {"coverage": 0.81, "coverage_worst_quarter_of_windows": 0.78}
    base = {"coverage": 0.79, "coverage_worst_quarter_of_windows": 0.70}
    assert decide(good, base, pinball_ci_low=-0.1)["candidate_for_production"] is True
    assert decide(good, base, pinball_ci_low=0.2)["candidate_for_production"] is False  # clearly worse pinball
    wide = {**good, "coverage": 0.90}
    assert decide(wide, base, -0.1)["candidate_for_production"] is False  # overall coverage too high
    no_help = {**good, "coverage_worst_quarter_of_windows": 0.69}
    assert decide(no_help, base, -0.1)["candidate_for_production"] is False  # worst windows no closer
