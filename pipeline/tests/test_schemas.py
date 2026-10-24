from __future__ import annotations

import pandas as pd
import pytest

from voltia.schemas import BatchValidationError, longest_gap, validate_daily, validate_hourly


def _daily(series: str, values: list[float], start: str = "2026-10-01") -> pd.DataFrame:
    days = pd.date_range(start, periods=len(values), freq="D")
    return pd.DataFrame({"series": series, "day": days, "value": values})


def test_valid_daily_batch_passes() -> None:
    frame = validate_daily(_daily("demand_kwh", [2.4e8, 2.5e8, 2.3e8]))
    assert len(frame) == 3


def test_value_out_of_range_is_rejected() -> None:
    with pytest.raises(BatchValidationError):
        validate_daily(_daily("reservoir_pct", [0.5, 1.7]))


def test_unknown_series_is_rejected() -> None:
    with pytest.raises(BatchValidationError):
        validate_daily(_daily("made_up", [1.0]))


def test_nan_is_rejected() -> None:
    with pytest.raises(BatchValidationError):
        validate_daily(_daily("demand_kwh", [2.4e8, float("nan")]))


def test_duplicates_are_rejected() -> None:
    frame = pd.concat([_daily("demand_kwh", [2.4e8]), _daily("demand_kwh", [2.5e8])])
    with pytest.raises(BatchValidationError, match="duplicated"):
        validate_daily(frame)


def test_long_gap_is_rejected_but_short_gap_is_not() -> None:
    base = _daily("demand_kwh", [2.4e8])
    short = pd.concat([base, _daily("demand_kwh", [2.4e8], start="2026-10-04")])  # 2 missing days
    long = pd.concat([base, _daily("demand_kwh", [2.4e8], start="2026-10-08")])  # 6 missing days
    assert len(validate_daily(short)) == 2
    with pytest.raises(BatchValidationError, match="gap"):
        validate_daily(long)


def test_monthly_series_can_skip_the_gap_check() -> None:
    monthly = pd.DataFrame(
        {"series": "oni", "day": pd.to_datetime(["2026-01-01", "2026-02-01"]), "value": [0.1, 0.4]}
    )
    assert len(validate_daily(monthly, continuous=False)) == 2


def test_longest_gap() -> None:
    days = pd.Series(pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-06"]))
    assert longest_gap(days) == 3


def test_hourly_validation() -> None:
    ok = pd.DataFrame(
        {
            "series": "price_cop_kwh",
            "day": pd.to_datetime(["2026-10-01"] * 2),
            "hour": [1, 2],
            "value": [500.0, 600.0],
        }
    )
    assert len(validate_hourly(ok)) == 2
    bad = ok.assign(hour=[1, 25])
    with pytest.raises(BatchValidationError):
        validate_hourly(bad)
