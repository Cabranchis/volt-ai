from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from voltia.explain import feature_labels
from voltia.features import (
    TARGETS,
    build_features,
    calendar_frame,
    feature_names,
    feature_table,
    oni_known,
)


@pytest.mark.parametrize("target", list(TARGETS))
def test_features_ignore_everything_after_the_origin(history: pd.DataFrame, target: str) -> None:
    origin = pd.Timestamp("2024-06-12")
    horizons = TARGETS[target].horizons
    before = build_features(history, origin, horizons, target)

    rng = np.random.default_rng(1)
    future = history.index > origin
    mutated = history.copy()
    mutated.loc[future] = mutated.loc[future] * rng.uniform(0.2, 5.0, size=(future.sum(), 1))
    mutated.loc[mutated.index[future][::3], "demand_kwh"] = np.nan
    after = build_features(mutated, origin, horizons, target)

    pd.testing.assert_frame_equal(before, after, check_exact=True)
    assert before["h"].tolist() == horizons
    assert (before["day"] == origin + pd.to_timedelta(before["h"], unit="D")).all()


@pytest.mark.parametrize("target", list(TARGETS))
def test_training_table_rows_equal_truncated_builds(history: pd.DataFrame, target: str) -> None:
    """The vectorised table used for training has no look-ahead either."""
    horizons = TARGETS[target].horizons
    table = feature_table(history, target, horizons)
    for origin in pd.to_datetime(["2024-01-31", "2024-07-04", "2025-01-02"]):
        full_rows = table[table["origin"] == origin].reset_index(drop=True)
        truncated = build_features(history.loc[:origin], origin, horizons, target)
        pd.testing.assert_frame_equal(full_rows, truncated, check_exact=True)


def test_feature_columns_are_complete(history: pd.DataFrame) -> None:
    table = feature_table(history, "demand_kwh", [1, 2])
    assert list(table.columns[:5]) == ["origin", "day", "ref_log", "sn_log", "last_log"]
    assert list(table.columns[5:]) == feature_names("demand_kwh")
    late = table[table["origin"] > pd.Timestamp("2024-03-01")]
    assert late[feature_names("demand_kwh")].notna().all().all()


def test_build_features_needs_the_origin_in_history(history: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="does not reach"):
        build_features(history, history.index[-1] + pd.Timedelta(days=1), [1], "demand_kwh")


def test_colombian_holidays_2024() -> None:
    cal = calendar_frame(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-12-31"))
    observed = [d.date() for d in cal.index[cal["is_holiday"] == 1]]
    expected = [
        date(2024, 1, 1),
        date(2024, 1, 8),
        date(2024, 3, 25),
        date(2024, 3, 28),
        date(2024, 3, 29),
        date(2024, 5, 1),
        date(2024, 5, 13),
        date(2024, 6, 3),
        date(2024, 6, 10),
        date(2024, 7, 1),
        date(2024, 7, 20),
        date(2024, 8, 7),
        date(2024, 8, 19),
        date(2024, 10, 14),
        date(2024, 11, 4),
        date(2024, 11, 11),
        date(2024, 12, 8),
        date(2024, 12, 25),
    ]
    assert observed == expected


def test_long_weekends_holy_week_and_holiday_distance() -> None:
    cal = calendar_frame(pd.Timestamp("2024-03-20"), pd.Timestamp("2024-04-02"))
    # Saturday 23 to Monday 25 March 2024 is a puente (San José moved to Monday).
    assert cal.loc["2024-03-23":"2024-03-25", "in_long_weekend"].tolist() == [1, 1, 1]
    assert cal.loc["2024-03-26", "in_long_weekend"] == 0
    assert cal.loc["2024-03-27", "is_nonworking"] == 0
    # Holy Week runs from Palm Sunday (24 March) to Easter Sunday (31 March).
    assert cal.loc["2024-03-24":"2024-03-31", "holy_week"].sum() == 8
    assert cal.loc["2024-03-23", "holy_week"] == 0
    assert cal.loc["2024-03-26", "days_to_holiday"] == 2
    assert cal.loc["2024-03-26", "days_from_holiday"] == 1
    assert cal.loc["2024-04-02", "days_to_holiday"] == 14  # capped
    christmas = calendar_frame(pd.Timestamp("2024-12-23"), pd.Timestamp("2025-01-02"))
    flagged = christmas.index[christmas["christmas_new_year"] == 1].strftime("%m-%d").tolist()
    assert flagged == ["12-24", "12-25", "12-31", "01-01"]


def test_oni_is_used_only_after_publication() -> None:
    index = pd.date_range("2026-06-01", "2026-10-21", freq="D")
    hist = pd.DataFrame({"oni": np.nan}, index=index)
    hist.loc["2026-07-01", "oni"] = 1.80
    hist.loc["2026-08-01", "oni"] = 2.16
    hist.loc["2026-09-01", "oni"] = 2.50  # stored, but not published by 21 October
    known = oni_known(hist)
    assert known.loc["2026-10-14"] == 1.80
    assert known.loc["2026-10-15"] == 2.16  # 1 August + 75 days
    assert known.loc["2026-10-21"] == 2.16
    assert np.isnan(known.loc["2026-06-30"])


def test_every_feature_has_spanish_and_english_labels() -> None:
    labels = feature_labels()
    for target in TARGETS:
        for name in feature_names(target):
            assert set(labels[name]) == {"es", "en"}, name
            assert labels[name]["es"]
            assert labels[name]["en"]
