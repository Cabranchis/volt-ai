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


@pytest.mark.parametrize(
    "block", (*features_ext.BLOCKS, *features_ext.PHASE_B_BLOCKS, *features_ext.MACRO_BLOCKS)
)
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


@pytest.mark.parametrize(
    ("block", "column"),
    [
        ("regional", "reg_reservoir_kwh_ANTIOQUIA"),
        ("profile", "price_peak"),
        ("restrictions", "restr_plain_cop"),
        ("availability", "dispo_real_thermal"),
        ("fx", "trm"),
        ("oil", "brent"),
    ],
)
def test_phase_b_scrambling_one_day_early_moves_the_block(data: pd.DataFrame, block: str, column: str) -> None:
    """Guard the guard for the phase B blocks: noise from one day before publication is seen."""
    origin = ORIGINS[2]
    original = _features_at(data, origin, (block,))
    early = data.copy()
    as_of = origin + pd.Timedelta(days=harness.SETTLE_LAG)
    cut = harness.known_through(column, as_of) - pd.Timedelta(days=1)
    later = early.index > cut
    early.loc[later, column] = early.loc[later, column] * 3 + 5
    assert not _features_at(early, origin, (block,)).equals(original)


def _ode_features_at(data: pd.DataFrame, origin: pd.Timestamp) -> pd.DataFrame:
    """The hydro_ode features of one origin for the whole horizon 1..14."""
    table = pd.DataFrame({"origin": origin, "h": np.arange(1, 15)})
    table["day"] = table["origin"] + pd.to_timedelta(table["h"], unit="D")
    return features_ext.add_blocks(table, data, ("hydro_ode",))


@pytest.mark.parametrize("origin", ORIGINS)
def test_hydro_ode_ignores_values_after_publication(data: pd.DataFrame, origin: pd.Timestamp) -> None:
    original = _ode_features_at(data, origin)
    mutated = _ode_features_at(_scramble_after_publication(data, origin, 17), origin)
    assert original.notna().all().all()
    pd.testing.assert_frame_equal(original, mutated)


@pytest.mark.parametrize("column", ["reservoir_kwh", "inflows_kwh", "inflows_hist_mean_kwh", "reservoir_capacity_kwh"])
def test_hydro_ode_scrambling_one_day_early_moves_it(data: pd.DataFrame, column: str) -> None:
    """Guard the guard: noise from the last published day on is seen by the projection."""
    origin = ORIGINS[2]
    original = _ode_features_at(data, origin)
    early = data.copy()
    as_of = origin + pd.Timedelta(days=harness.SETTLE_LAG)
    cut = harness.known_through(column, as_of) - pd.Timedelta(days=1)
    later = early.index > cut
    early.loc[later, column] = early.loc[later, column] * 3 + 5
    assert not _ode_features_at(early, origin).equals(original)


def _synthetic_water(anomaly: float, years: int = 4) -> pd.DataFrame:
    index = pd.date_range("2019-01-01", periods=365 * years, freq="D")
    climate = 100.0 + 20.0 * np.sin(2 * np.pi * (index.dayofyear.to_numpy() - 30) / 365)
    inflow = climate * np.exp(anomaly)
    return pd.DataFrame(
        {
            "reservoir_kwh": 5000.0,  # constant: the net outflow equals the inflow
            "reservoir_capacity_kwh": 10000.0,
            "inflows_kwh": inflow,
            "inflows_hist_mean_kwh": climate,
        },
        index=index,
    )


def test_hydro_ode_is_flat_when_the_inflows_are_the_average_and_nothing_leaves_but_them() -> None:
    water = _synthetic_water(0.0)
    origin = water.index[-40]
    target, change = features_ext.hydro_ode_projection(water)
    # No anomaly and a volume that does not change: the net outflow is the inflow, so the level stays.
    assert target.loc[origin].to_numpy() == pytest.approx(0.5, abs=0.02)
    assert change.loc[origin].to_numpy() == pytest.approx(0.0, abs=0.02)


def test_hydro_ode_matches_the_numerical_solution_of_the_equation() -> None:
    from scipy.integrate import solve_ivp

    water = _synthetic_water(0.3)
    origin = water.index[-40]
    target, _ = features_ext.hydro_ode_projection(water)
    k = features_ext._k("reservoir_kwh", features_ext.PUBLICATION_LAG)
    day0 = origin + pd.Timedelta(days=k)
    # The persistence of the anomaly, estimated from the days up to day0 the way the block does it.
    anomaly = np.log(water["inflows_kwh"].rolling(7, min_periods=5).mean() / water["inflows_hist_mean_kwh"].rolling(7, min_periods=5).mean())
    phi = anomaly.expanding(min_periods=features_ext.ODE_MIN_HISTORY).corr(anomaly.shift(1)).clip(0.5, 0.995)
    tau = -1.0 / np.log(float(phi.fillna(features_ext.ODE_DEFAULT_PHI).loc[day0]))
    # The volume is constant, so I - dV = I, and the net outflow is its mean over the 28 days up to day0.
    outflow = float(water["inflows_kwh"].loc[day0 - pd.Timedelta(days=27) : day0].mean())
    climate = water["inflows_hist_mean_kwh"]

    def rate(t: float, v: np.ndarray) -> list[float]:
        # Inflow of day t after day0: the mean of the same day a year earlier times exp(anomaly).
        step = int(np.ceil(t - 1e-9))  # inflows are daily values: the whole day s has the anomaly of day s
        day = day0 + pd.Timedelta(days=step)
        mean = float(climate.loc[day - pd.Timedelta(days=features_ext.ODE_DAYS_PER_YEAR)])
        return [mean * np.exp(0.3 * np.exp(-step / tau)) - outflow]

    solved = solve_ivp(rate, (0.0, 12.0), [5000.0], t_eval=np.arange(0, 13), max_step=0.25)
    for h in (k + 1, k + 6, 14):
        assert float(target.loc[origin, h]) == pytest.approx(solved.y[0][h - k] / 10000.0, abs=0.002)
