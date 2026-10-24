from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from voltia.features import TargetSpec
from voltia.models.backtest import calibrate_online
from voltia.models.calibration import Offset, apply_offset, conformal_offset

SPEC = TargetSpec("y", 5, ((1, 5),))


def test_conformal_offset_hand_example() -> None:
    lower = np.zeros(9)
    upper = np.ones(9)
    actual = np.array([-0.5, 0.2, 0.4, 0.5, 0.6, 0.8, 1.1, 1.3, 1.6])
    off = conformal_offset(lower, upper, actual, 0.2, 0.2)
    # ceil(10 * 0.8) / 9 = 8/9 -> 8th smallest score ("higher" method)
    lo_scores = np.sort(lower - actual)
    hi_scores = np.sort(actual - upper)
    assert off.lower == pytest.approx(lo_scores[7])
    assert off.upper == pytest.approx(hi_scores[7])
    assert off.n == 9
    assert conformal_offset([np.nan], [np.nan], [np.nan]) == Offset()


def test_apply_offset_keeps_quantiles_ordered_even_when_shrinking() -> None:
    q = np.array([[1.0, 2.0, 3.0], [0.0, 0.1, 0.2]])
    out = apply_offset(q, Offset(lower=-5.0, upper=-5.0))
    assert np.all(out[:, 0] <= out[:, 1])
    assert np.all(out[:, 1] <= out[:, 2])
    assert np.array_equal(out[:, 1], q[:, 1])


def _rows(n_origins: int, rng: np.random.Generator) -> pd.DataFrame:
    """A miscalibrated model: the truth is N(0, 1) in log units, bounds are +-0.5."""
    origins = pd.date_range("2024-01-01", periods=n_origins, freq="10D")
    frames = []
    for origin in origins:
        h = np.arange(1, 6)
        frames.append(
            pd.DataFrame(
                {
                    "origin": origin,
                    "h": h,
                    "day": origin + pd.to_timedelta(h, unit="D"),
                    "bucket": "1-5",
                    "q10_log": -0.5,
                    "q50_log": 0.0,
                    "q90_log": 0.5,
                    "y": np.exp(rng.normal(0, 1, 5)),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def _coverage(rows: pd.DataFrame, lo: str, hi: str) -> float:
    return float(((rows["y"] >= rows[lo]) & (rows["y"] <= rows[hi])).mean())


def test_online_cqr_restores_coverage_without_future_data() -> None:
    rows = _rows(120, np.random.default_rng(0))
    out = calibrate_online(rows, min_origins=4, spec=SPEC)
    scored = out[out["calibrated"]]
    raw = float(
        (
            (scored["y"] >= np.exp(scored["q10_log"])) & (scored["y"] <= np.exp(scored["q90_log"]))
        ).mean()
    )
    assert raw < 0.45  # +-0.5 sd covers about 38 %
    assert 0.74 <= _coverage(scored, "m10", "m90") <= 0.86
    assert not out[out["origin"] < out["origin"].unique()[4]]["calibrated"].any()
    assert (out["m10"] <= out["m50"]).all()
    assert (out["m50"] <= out["m90"]).all()

    # Changing the outcomes of later origins must not move earlier calibrated bounds.
    cut = out["origin"].unique()[60]
    changed = rows.copy()
    changed.loc[changed["origin"] >= cut, "y"] *= 50
    again = calibrate_online(changed, min_origins=4, spec=SPEC)
    early = out["origin"] < cut
    pd.testing.assert_frame_equal(
        out.loc[early, ["m10", "m50", "m90"]], again.loc[early, ["m10", "m50", "m90"]]
    )
