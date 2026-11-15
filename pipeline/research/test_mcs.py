"""Checks of the Model Confidence Set on losses whose answer is known.

Run with: uv run pytest research/test_mcs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from mcs import mcs  # noqa: E402


def _losses(shifts: dict[str, float], n: int = 120, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    common = rng.normal(0, 1, n)  # an easy and a hard origin affect every method alike
    return pd.DataFrame({name: 2 + shift + common + rng.normal(0, 0.3, n) for name, shift in shifts.items()})


def test_a_clearly_worse_method_leaves_the_set_and_equals_stay():
    result = mcs(_losses({"a": 0.0, "b": 0.0, "bad": 1.5}))
    assert bool(result.loc["a", "in_set"]) and bool(result.loc["b", "in_set"])
    assert not bool(result.loc["bad", "in_set"])


def test_a_single_best_method_is_alone():
    result = mcs(_losses({"best": 0.0, "mid": 1.0, "bad": 2.0}))
    assert list(result.index[result["in_set"]]) == ["best"]


def test_identical_methods_all_stay():
    base = _losses({"a": 0.0})["a"]
    same = pd.DataFrame({"a": base, "b": base + 0.0, "c": base + 0.0})
    assert mcs(same)["in_set"].all()


def test_same_seed_same_answer_and_p_values_are_probabilities():
    losses = _losses({"a": 0.0, "b": 0.2, "c": 0.9})
    first, second = mcs(losses), mcs(losses)
    pd.testing.assert_frame_equal(first, second)
    assert first["p_value"].between(0, 1).all()


def test_errors_on_unusable_input():
    with pytest.raises(ValueError, match="at least two"):
        mcs(pd.DataFrame({"a": np.arange(20.0)}))
    with pytest.raises(ValueError, match="complete"):
        mcs(pd.DataFrame({"a": [np.nan] * 20, "b": np.arange(20.0)}))
    with pytest.raises(ValueError, match="too few"):
        mcs(pd.DataFrame({"a": np.arange(5.0), "b": np.arange(5.0) + 1}))


def test_rarely_drops_the_best_when_all_are_equal():
    """Level check: with equal methods the set should contain all of them in about 1 - alpha of the runs."""
    kept = 0
    runs = 60
    for seed in range(runs):
        rng = np.random.default_rng(100 + seed)
        common = rng.normal(0, 1, 100)
        frame = pd.DataFrame({m: common + rng.normal(0, 0.5, 100) for m in "abc"})
        kept += bool(mcs(frame, n_boot=500, seed=seed)["in_set"].all())
    assert kept / runs >= 0.8


def test_a_method_that_is_worse_at_every_origin_by_the_same_amount_leaves():
    """A difference that never moves across resamples (standard error 0) is not 'no difference'."""
    n = 20
    result = mcs(pd.DataFrame({"a": np.zeros(n), "b": np.ones(n)}))
    assert bool(result.loc["a", "in_set"]) and not bool(result.loc["b", "in_set"])


def test_the_last_method_has_p_one_and_a_worse_method_never_has_a_larger_p():
    result = mcs(_losses({"best": 0.0, "mid": 0.4, "bad": 1.5}))
    assert result.loc["best", "p_value"] == 1.0
    p_by_loss = result.sort_values("mean_loss")["p_value"].tolist()
    assert p_by_loss == sorted(p_by_loss, reverse=True)
