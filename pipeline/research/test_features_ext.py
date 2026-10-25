"""Leakage guard for the experimental feature blocks.

For each origin T, every value a series publishes after day `A - lag` (A = T + SETTLE_LAG) is
replaced with noise; the features of that origin must not move.
Run with: uv run pytest research/test_features_ext.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))

import features_ext  # noqa: E402
import harness  # noqa: E402

ORIGINS = [pd.Timestamp(d) for d in ("2021-03-10", "2022-06-15", "2023-09-01")]


@pytest.fixture(scope="module")
def data() -> pd.DataFrame:
    return harness.load_data()


def _features_at(data: pd.DataFrame, origin: pd.Timestamp, blocks: tuple[str, ...]) -> pd.DataFrame:
    """Origin-level and per-row (h = 1..5) features of one origin."""
    table = pd.DataFrame({"origin": origin, "h": np.arange(1, 6)})
    table["day"] = table["origin"] + pd.to_timedelta(table["h"], unit="D")
    return features_ext.add_blocks(table, data, blocks)


def _scramble_after_publication(data: pd.DataFrame, origin: pd.Timestamp, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    mutated = data.copy()
    as_of = origin + pd.Timedelta(days=harness.SETTLE_LAG)
    for name in harness.PUBLICATION_LAG:
        if name not in mutated.columns:
            continue
        later = mutated.index > harness.known_through(name, as_of)
        values = mutated.loc[later, name].to_numpy(dtype=float)
        mutated.loc[later, name] = values * rng.uniform(2.0, 5.0, size=values.shape) + 1.0
    return mutated


@pytest.mark.parametrize("block", features_ext.BLOCKS)
@pytest.mark.parametrize("origin", ORIGINS)
def test_block_ignores_values_after_publication(
    data: pd.DataFrame, block: str, origin: pd.Timestamp
) -> None:
    original = _features_at(data, origin, (block,))
    mutated = _features_at(_scramble_after_publication(data, origin, 11), origin, (block,))
    pd.testing.assert_frame_equal(original, mutated)


def test_scrambling_actually_changes_something(data: pd.DataFrame) -> None:
    """Guard the guard: the same noise applied one day too early must move the dispatch features."""
    origin = ORIGINS[1]
    original = _features_at(data, origin, ("dispatch",))
    early = data.copy()
    as_of = origin + pd.Timedelta(days=harness.SETTLE_LAG)
    cut = harness.known_through("dispatch_cost", as_of) - pd.Timedelta(days=1)
    later = early.index > cut
    early.loc[later, "dispatch_cost"] = early.loc[later, "dispatch_cost"] * 3 + 5
    assert not _features_at(early, origin, ("dispatch",)).equals(original)
