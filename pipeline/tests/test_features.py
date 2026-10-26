from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from voltia import features as features_module
from voltia.explain import feature_labels
from voltia.features import (
    MARKET_FEATURES,
    SETTLE_LAG_DAYS,
    TARGETS,
    build_features,
    calendar_frame,
    days_known_past_origin,
    feature_names,
    feature_table,
    log_positive,
    oni_known,
)

ORIGINS = ["2024-01-31", "2024-06-12"]  # spilling is positive around the first one


def assert_ignores_unpublished(
    history: pd.DataFrame, origin: pd.Timestamp, target: str, column: str
) -> None:
    """Corrupt `column` from the first day not yet published at the forecast date."""
    horizons = TARGETS[target].horizons
    before = build_features(history, origin, horizons, target)
    rng = np.random.default_rng(1)
    mutated = history.copy()
    usable_until = origin + pd.Timedelta(days=days_known_past_origin(column))
    later = mutated.index > usable_until
    # additive noise: a multiplicative change would leave a column that is 0 there unchanged
    mutated.loc[later, column] = mutated.loc[later, column] + rng.uniform(1e3, 1e9, later.sum())
    after = build_features(mutated, origin, horizons, target)
    pd.testing.assert_frame_equal(before, after, check_exact=True)
    assert before["h"].tolist() == horizons
    assert (before["day"] == origin + pd.to_timedelta(before["h"], unit="D")).all()


@pytest.mark.parametrize("origin", ORIGINS)
@pytest.mark.parametrize("target", list(TARGETS))
def test_features_ignore_everything_not_yet_published(
    history: pd.DataFrame, target: str, origin: str
) -> None:
    """Each series is corrupted on its own, from the first day XM has not published by then."""
    for column in history.columns:
        assert_ignores_unpublished(history, pd.Timestamp(origin), target, column)


def test_the_leakage_check_fails_when_a_lag_is_too_short(
    history: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard the guard: the features read a day beyond what is published, as if the lag were 0."""
    real = features_module.days_known_past_origin
    monkeypatch.setattr(
        features_module,
        "days_known_past_origin",
        lambda s: real(s) + 1 if s == "dispatch_cost" else real(s),
    )
    with pytest.raises(AssertionError):
        assert_ignores_unpublished(
            history, pd.Timestamp("2024-06-12"), "price_mean_cop_kwh", "dispatch_cost"
        )


@pytest.mark.parametrize("target", list(TARGETS))
def test_training_table_rows_equal_truncated_builds(history: pd.DataFrame, target: str) -> None:
    """The vectorised table used for training has no look-ahead either."""
    horizons = TARGETS[target].horizons
    table = feature_table(history, target, horizons)
    for origin in pd.to_datetime(["2024-01-31", "2024-07-04", "2025-01-02"]):
        full_rows = table[table["origin"] == origin].reset_index(drop=True)
        seen = history.loc[: origin + pd.Timedelta(days=SETTLE_LAG_DAYS)]
        truncated = build_features(seen, origin, horizons, target)
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


def test_market_features_exist_only_for_the_price(history: pd.DataFrame) -> None:
    assert set(MARKET_FEATURES) == {"price_mean_cop_kwh"}
    assert set(MARKET_FEATURES["price_mean_cop_kwh"]) <= set(feature_names("price_mean_cop_kwh"))
    assert not set(MARKET_FEATURES["price_mean_cop_kwh"]) & set(feature_names("demand_kwh"))


def test_dispatch_cost_prices_the_days_xm_has_not_settled(history: pd.DataFrame) -> None:
    """With a one-day publication lag the cost is read for h = 1 and 2, never beyond."""
    origin = pd.Timestamp("2024-06-12")
    horizons = TARGETS["price_mean_cop_kwh"].horizons
    rows = build_features(history, origin, horizons, "price_mean_cop_kwh")
    known_days = SETTLE_LAG_DAYS - 1
    assert known_days == days_known_past_origin("dispatch_cost")
    assert rows.loc[rows["h"] <= known_days, "dc_target_rel"].notna().all()
    assert rows.loc[rows["h"] > known_days, "dc_target_rel"].isna().all()
    assert rows.loc[rows["h"] > known_days, "dc_corrected_target_rel"].isna().all()
    cost = log_positive(history["dispatch_cost"])
    expected = cost.loc[origin + pd.Timedelta(days=1)] - rows["ref_log"].iloc[0]
    assert rows.loc[rows["h"] == 1, "dc_target_rel"].iloc[0] == pytest.approx(expected)


def test_the_last_published_day_does_feed_the_features(history: pd.DataFrame) -> None:
    origin = pd.Timestamp("2024-06-12")
    horizons = TARGETS["price_mean_cop_kwh"].horizons
    before = build_features(history, origin, horizons, "price_mean_cop_kwh")
    mutated = history.copy()
    last_usable = origin + pd.Timedelta(days=days_known_past_origin("dispatch_cost"))
    mutated.loc[mutated.index == last_usable, "dispatch_cost"] *= 3.0
    after = build_features(mutated, origin, horizons, "price_mean_cop_kwh")
    assert not before.equals(after)


def test_missing_market_series_leave_nan_features_not_errors(history: pd.DataFrame) -> None:
    bare = history.drop(columns=["dispatch_cost", "contract_price", "spill_kwh"])
    rows = build_features(bare, pd.Timestamp("2024-06-12"), [1, 2, 3], "price_mean_cop_kwh")
    assert rows["dc_target_rel"].isna().all()
    assert rows["contract_rel"].isna().all()
    assert rows["level_last_rel"].notna().all()
