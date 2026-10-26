"""Validation of batches before they reach the database (requirement FR-03)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

# Plausible (min, max) per daily series. A value outside is a data error, not an outlier to model.
DAILY_BOUNDS: dict[str, tuple[float, float]] = {
    "demand_kwh": (50e6, 400e6),
    "price_mean_cop_kwh": (0.0, 20_000.0),
    "price_max_cop_kwh": (0.0, 20_000.0),
    "reservoir_pct": (0.0, 1.0),
    "reservoir_kwh": (0.0, 30e9),
    "inflows_kwh": (0.0, 1.5e9),
    "inflows_pct": (0.0, 10.0),
    "inflows_hist_mean_kwh": (0.0, 1.5e9),
    "gen_total_kwh": (50e6, 400e6),
    "gen_hydro_kwh": (0.0, 400e6),
    "gen_thermal_kwh": (0.0, 400e6),
    "gen_solar_kwh": (0.0, 400e6),
    "gen_wind_kwh": (0.0, 400e6),
    "gen_cogen_kwh": (0.0, 400e6),
    "gen_other_kwh": (0.0, 400e6),
    "weather_temp_c": (-5.0, 40.0),
    "weather_precip_mm": (0.0, 500.0),
    "oni": (-4.0, 4.0),
    "dispatch_cost": (0.0, 20_000.0),
    "contract_price": (0.0, 5_000.0),
    "contract_price_unreg": (0.0, 5_000.0),
    "scarcity_price": (0.0, 5_000.0),
    "spill_kwh": (0.0, 2e9),
    "turbined_m3": (0.0, 2e10),
    "reservoir_capacity_kwh": (0.0, 40e9),
}

HOURLY_BOUNDS: dict[str, tuple[float, float]] = {
    "price_cop_kwh": (0.0, 20_000.0),
    "generation_kwh": (1e6, 40e6),
}

# Metrics reported per reservoir or river (table entity_daily).
ENTITY_BOUNDS: dict[str, tuple[float, float]] = {
    "reservoir_kwh": (0.0, 10e9),
    "reservoir_capacity_kwh": (0.0, 10e9),
    "inflows_kwh": (0.0, 1.5e9),
    "inflows_hist_mean_kwh": (0.0, 1.5e9),
}

# A daily series may miss at most this many consecutive days inside a batch.
MAX_GAP_DAYS = 3


class BatchValidationError(ValueError):
    """The batch is rejected as a whole; nothing is written."""


def _within_bounds(frame: pd.DataFrame, bounds: dict[str, tuple[float, float]]) -> pd.Series:
    low = frame["series"].map({k: v[0] for k, v in bounds.items()})
    high = frame["series"].map({k: v[1] for k, v in bounds.items()})
    return (frame["value"] >= low) & (frame["value"] <= high)


def _schema(
    bounds: dict[str, tuple[float, float]], extra: dict[str, pa.Column]
) -> pa.DataFrameSchema:
    return pa.DataFrameSchema(
        {
            "series": pa.Column(str, pa.Check.isin(list(bounds))),
            "day": pa.Column("datetime64[ns]"),
            "value": pa.Column(float, nullable=False),
            **extra,
        },
        checks=[
            pa.Check(lambda df: np.isfinite(df["value"]), error="value must be finite"),
            pa.Check(
                lambda df: _within_bounds(df, bounds),
                error="value outside the plausible range for its series",
            ),
        ],
        strict=True,
        coerce=True,
    )


_DAILY = _schema(DAILY_BOUNDS, {})
_ENTITY = pa.DataFrameSchema(
    {
        "metric": pa.Column(str, pa.Check.isin(list(ENTITY_BOUNDS))),
        "entity": pa.Column(str, pa.Check.str_length(min_value=1)),
        "day": pa.Column("datetime64[ns]"),
        "value": pa.Column(float, nullable=False),
    },
    checks=[
        pa.Check(lambda df: np.isfinite(df["value"]), error="value must be finite"),
        pa.Check(
            lambda df: (
                (df["value"] >= df["metric"].map({k: v[0] for k, v in ENTITY_BOUNDS.items()}))
                & (df["value"] <= df["metric"].map({k: v[1] for k, v in ENTITY_BOUNDS.items()}))
            ),
            error="value outside the plausible range for its metric",
        ),
    ],
    strict=True,
    coerce=True,
)
_HOURLY = _schema(HOURLY_BOUNDS, {"hour": pa.Column(int, pa.Check.in_range(1, 24))})


def _run(schema: pa.DataFrameSchema, frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    try:
        checked = schema.validate(frame, lazy=True)
    except SchemaErrors as exc:
        failures = exc.failure_cases.head(5).to_dict("records")
        raise BatchValidationError(f"schema violations: {failures}") from exc
    duplicated = checked.duplicated(subset=keys, keep=False)
    if duplicated.any():
        raise BatchValidationError(f"{int(duplicated.sum())} duplicated rows for keys {keys}")
    return checked


def validate_daily(frame: pd.DataFrame, continuous: bool = True) -> pd.DataFrame:
    """Validate a long daily frame (series, day, value). Raises BatchValidationError."""
    checked = _run(_DAILY, frame, ["series", "day"])
    if continuous:
        for name, group in checked.groupby("series"):
            gap = longest_gap(group["day"])
            if gap > MAX_GAP_DAYS:
                raise BatchValidationError(f"{name}: gap of {gap} consecutive missing days")
    return checked


def validate_entities(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate a long frame (metric, entity, day, value) of per-reservoir or per-river values."""
    return _run(_ENTITY, frame, ["metric", "entity", "day"])


def validate_hourly(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate a long hourly frame (series, day, hour, value). Raises BatchValidationError."""
    return _run(_HOURLY, frame, ["series", "day", "hour"])


def longest_gap(days: pd.Series) -> int:
    """Longest run of missing calendar days between the first and last day of the series."""
    unique = pd.DatetimeIndex(days).unique().sort_values()
    if len(unique) < 2:
        return 0
    steps = (unique[1:] - unique[:-1]).days
    return int(max(steps.max() - 1, 0))
