from __future__ import annotations

import numpy as np
import pytest

from voltia.explain import shap_values, top_drivers
from voltia.models.gbm import GBMParams, fit_quantiles


def test_top_drivers_orders_by_magnitude_and_converts_to_target_units() -> None:
    phi = np.array([[0.1, -0.3, 0.02, 0.0, 0.05, -0.01]])
    names = ["a", "b", "c", "d", "e", "f"]
    drivers = top_drivers(phi, np.array([200.0]), names)[0]
    assert [d["feature"] for d in drivers] == ["b", "a", "e", "c", "f"]
    assert drivers[0]["direction"] == "down"
    assert drivers[1]["direction"] == "up"
    # Removing b's term (-0.3 in log units) would raise the forecast: 200 * (1 - e^0.3) < 0.
    assert drivers[0]["contribution"] == pytest.approx(200 * (1 - np.exp(0.3)))
    assert drivers[1]["contribution"] == pytest.approx(200 * (1 - np.exp(-0.1)))


def test_shap_values_add_up_to_the_raw_prediction() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(400, 3))
    z = 2 * x[:, 0] - x[:, 1] + rng.normal(0, 0.1, 400)
    booster = fit_quantiles(x, z, GBMParams(num_boost_round=30), ["a", "b", "c"], (0.5,))[0]
    phi = shap_values(booster, x[:20])
    raw = booster.predict(x[:20].astype(np.float32))
    assert phi.shape == (20, 3)
    base = raw - phi.sum(axis=1)
    assert np.allclose(base, base[0], atol=1e-6)
    assert np.abs(phi[:, 0]).mean() > np.abs(phi[:, 2]).mean()
