from __future__ import annotations

import pandas as pd
import pytest

from voltia.models import metrics


def test_point_metrics_against_hand_values() -> None:
    y = [100.0, 200.0, 400.0]
    yhat = [110.0, 180.0, 400.0]
    # |e|/y = 0.1, 0.1, 0 -> 6.667 %
    assert metrics.mape(y, yhat) == pytest.approx(20 / 3)
    # 2|e|/(|y|+|yhat|) = 20/210, 40/380, 0
    assert metrics.smape(y, yhat) == pytest.approx((20 / 210 + 40 / 380) / 3 * 100)
    # MAE = 10, scale 5 -> 2
    assert metrics.mase(y, yhat, 5.0) == pytest.approx(2.0)
    assert metrics.mase(y, yhat, [10.0, 20.0, 1.0]) == pytest.approx((1 + 1 + 0) / 3)


def test_mase_scale_is_the_seasonal_naive_in_sample_mae() -> None:
    series = pd.Series([1.0, 2, 3, 4, 5, 6, 7, 3, 2, 3, 4, 5, 6, 9])
    # |y_t - y_{t-7}| for t = 7..13: 2, 0, 0, 0, 0, 0, 2
    assert metrics.mase_scale(series, m=7) == pytest.approx(4 / 7)
    with pytest.raises(ValueError, match="not enough"):
        metrics.mase_scale(pd.Series([1.0, 2.0]), m=7)


def test_pinball_and_coverage() -> None:
    y = [10.0, 10.0, 10.0, 10.0]
    q = [8.0, 12.0, 10.0, 9.0]
    # alpha 0.9: 0.9*2, 0.1*2, 0, 0.9*1 -> 2.9 / 4
    assert metrics.pinball(y, q, 0.9) == pytest.approx(2.9 / 4)
    # alpha 0.1: 0.1*2, 0.9*2, 0, 0.1*1 -> 2.1 / 4
    assert metrics.pinball(y, q, 0.1) == pytest.approx(2.1 / 4)
    assert metrics.coverage([1.0, 5.0, 9.0, 3.0], [0, 6, 8, 3], [2, 7, 10, 3]) == 0.75


def test_shape_mismatch_is_an_error() -> None:
    with pytest.raises(ValueError, match="shape"):
        metrics.mape([1.0, 2.0], [1.0])
