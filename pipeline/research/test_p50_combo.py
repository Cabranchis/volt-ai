from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from run_p50_combo import BUCKETS, combine, decide, losses_for, origin_mase


def _rows(n_origins: int = 12, per_origin: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    records = []
    for o in range(n_origins):
        for h in range(1, per_origin + 1):
            y = 100 + rng.normal(0, 5)
            records.append(
                {
                    "origin": f"2025-01-{o + 1:02d}",
                    "h": h,
                    "bucket": "1-3",
                    "y": y,
                    "scale": 4.0,
                    "m50": y + rng.normal(0, 4),
                    "ets50": y + rng.normal(0, 8),
                    "persist": y + rng.normal(0, 8),
                }
            )
    return pd.DataFrame(records)


def test_combine_is_the_weighted_geometric_mean() -> None:
    rows = pd.DataFrame({"m50": [100.0], "ets50": [400.0], "persist": [25.0]})
    third = 1 / 3
    got = combine(rows, {"model": third, "ets": third, "last_price": third})
    assert got.iloc[0] == pytest.approx((100.0 * 400.0 * 25.0) ** third)
    half = combine(rows, {"model": 0.5, "last_price": 0.5})
    assert half.iloc[0] == pytest.approx(50.0)  # sqrt(100 * 25)


def test_the_weights_must_add_up_to_one() -> None:
    rows = pd.DataFrame({"m50": [1.0], "ets50": [1.0], "persist": [1.0]})
    with pytest.raises(ValueError, match="add up to one"):
        combine(rows, {"model": 0.5, "ets": 0.4})


def test_a_perfect_source_gets_a_zero_loss_and_a_blend_sits_between() -> None:
    rows = _rows()
    rows["m50"] = rows["y"]  # the model is exact
    losses = losses_for(rows, None)
    assert losses["model"].max() == pytest.approx(0.0, abs=1e-12)
    assert (losses["C2"] > 0).all()
    assert (losses["C2"] <= losses["last_price"] + 1e-9).all()  # half the weight is exact


def test_origin_mase_scales_by_the_origin_scale() -> None:
    rows = pd.DataFrame({"origin": ["a", "a"], "y": [10.0, 10.0], "scale": [2.0, 2.0]})
    assert origin_mase(rows, pd.Series([12.0, 8.0])).iloc[0] == pytest.approx(1.0)


def test_an_origin_missing_a_source_is_dropped_for_every_method() -> None:
    rows = _rows()
    rows.loc[rows["origin"] == "2025-01-03", "ets50"] = np.nan
    losses = losses_for(rows, None)
    assert "2025-01-03" not in losses.index
    assert len(losses) == 11


def _slices(whole_hi: float, bucket_lo: float) -> dict[str, dict[str, dict[str, float]]]:
    base = {"diff_vs_model": -0.05, "ci95_low": -0.2, "ci95_high": whole_hi}
    slices = {"all horizons": {"C1": dict(base)}}
    for b in BUCKETS:
        slices[b] = {"C1": {"diff_vs_model": 0.0, "ci95_low": bucket_lo, "ci95_high": 0.1}}
    return slices


def test_the_rule_needs_an_interval_below_zero_and_no_bucket_clearly_worse() -> None:
    assert decide(_slices(-0.01, -0.1), "C1")["candidate_for_production"] is True
    assert decide(_slices(0.02, -0.1), "C1")["candidate_for_production"] is False  # includes zero
    worse = decide(_slices(-0.01, 0.01), "C1")  # every bucket clearly worse
    assert worse["candidate_for_production"] is False
    assert worse["ii_buckets_clearly_worse"] == BUCKETS
