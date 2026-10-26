from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from conftest import make_history
from voltia.features import TargetSpec, build_features
from voltia.forecast import (
    TrainResult,
    forecast_target,
    load_models,
    observed_origin,
    save_models,
    train,
)
from voltia.models.backtest import (
    BacktestConfig,
    ModelConfig,
    anchored_origins,
    block_bootstrap_ci,
    prepare,
    reference_offset,
    select_origins,
    training_mask,
)
from voltia.models.gbm import GBMParams, fit_quantiles, predict_quantiles

FAST = GBMParams(num_boost_round=25, num_leaves=7, min_data_in_leaf=20)
SMALL = BacktestConfig(
    n_origins=2, n_warmup=1, step_days=20, anchor=None, min_calibration_origins=1
)
TARGETS = {
    "demand_kwh": TargetSpec("demand_kwh", 10, ((1, 5), (6, 10))),
    "price_mean_cop_kwh": TargetSpec("price_mean_cop_kwh", 5, ((1, 5),)),
}


@pytest.fixture(scope="module")
def trained() -> TrainResult:
    return train(make_history(days=560), FAST, SMALL, TARGETS)


def test_select_origins_are_evenly_spaced_and_leave_room_for_the_horizon() -> None:
    origins = select_origins(pd.Timestamp("2026-10-21"), 30, 4, 45)
    assert origins[-1] == pd.Timestamp("2026-09-21")
    assert [(b - a).days for a, b in itertools.pairwise(origins)] == [45, 45, 45]


def test_anchored_origins_only_grow_at_the_end() -> None:
    anchor = pd.Timestamp("2023-11-21")
    early = anchored_origins(anchor, pd.Timestamp("2026-10-20"), 30, 15, 3)
    later = anchored_origins(anchor, pd.Timestamp("2026-10-27"), 30, 15, 3)
    assert early == later[: len(early)]  # a week of new data adds none that already exist
    assert len(later) >= len(early)
    assert later[3] == anchor
    assert [(b - a).days for a, b in itertools.pairwise(later)] == [15] * (len(later) - 1)
    assert later[-1] <= pd.Timestamp("2026-10-27") - pd.Timedelta(days=30)
    assert later[-1] + pd.Timedelta(days=15) > pd.Timestamp("2026-10-27") - pd.Timedelta(days=30)


def test_block_bootstrap_interval_brackets_the_mean_and_widens_with_dependence() -> None:
    diff = np.sin(np.arange(60) / 4) + 0.2
    lo, hi = block_bootstrap_ci(diff, 1)
    assert lo < diff.mean() < hi
    assert (lo, hi) == block_bootstrap_ci(diff, 1)  # fixed seed
    wide = block_bootstrap_ci(diff, 8)
    assert wide[1] - wide[0] > hi - lo  # a slowly varying series is not 60 independent draws


def test_block_bootstrap_interval_is_undefined_without_enough_origins() -> None:
    lo, hi = block_bootstrap_ci(np.array([0.3, -0.1]), 3)
    assert np.isnan(lo)
    assert np.isnan(hi)
    assert all(np.isnan(v) for v in block_bootstrap_ci(np.array([0.3]), 1))


def test_train_on_the_calendar_keeps_warmup_before_the_anchor_and_counts_origins() -> None:
    history = make_history(days=560)
    cfg = BacktestConfig(n_warmup=1, step_days=30, anchor="2024-03-01", min_calibration_origins=1)
    result = train(history, FAST, cfg, TARGETS)
    backtest = result.metrics["backtest"]
    assert backtest["warmup_origins"] == ["2024-01-31"]
    assert backtest["origins"][0] == "2024-03-01"
    assert backtest["n_origins"] == len(backtest["origins"])
    assert result.metrics["targets"]["demand_kwh"]["n_origins"] == len(backtest["origins"])


def test_train_rejects_origins_closer_than_the_week_they_can_move(history: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="at least 8"):
        train(history, FAST, BacktestConfig(step_days=7), TARGETS)


def test_training_rows_never_reach_past_the_cutoff(history: pd.DataFrame) -> None:
    spec = TargetSpec("demand_kwh", 30, ((1, 30),))
    prepared = prepare(history, spec, ModelConfig())
    cutoff = pd.Timestamp("2024-05-01")
    mask = training_mask(prepared, cutoff)
    assert mask.any()
    assert (prepared.table.loc[mask, "day"] <= cutoff).all()
    assert prepared.table.loc[mask, "origin"].max() == cutoff - pd.Timedelta(days=1)


def test_quantile_predictions_never_cross() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(600, 3))
    z = x[:, 0] + rng.normal(0, 1, 600)
    boosters = fit_quantiles(x, z, FAST, ["a", "b", "c"])
    q = predict_quantiles(boosters, rng.normal(size=(200, 3)))
    assert np.all(np.diff(q, axis=1) >= 0)


def test_train_reports_model_and_baselines(trained: TrainResult) -> None:
    metrics = trained.metrics
    demand = metrics["targets"]["demand_kwh"]
    assert demand["n_origins"] == 2
    assert set(demand["overall"]) == {"model", "model_raw", "seasonal_naive", "ets"}
    assert set(demand["by_bucket"]) == {"1-5", "6-10"}
    assert set(demand["paired"]) == {"seasonal_naive", "ets"}
    assert (
        demand["paired"]["ets"]["mase_diff_ci95"] is None
    )  # two origins are too few for an interval
    assert len(demand["by_origin"]) == 2
    for key in ("mape", "smape", "mase", "pinball_p10", "pinball_p50", "pinball_p90"):
        assert np.isfinite(demand["overall"]["model"][key])
    assert 0 <= demand["coverage"]["calibrated"] <= 1
    assert metrics["backtest"]["warmup_origins"]
    assert metrics["backtest"]["origins"]
    # The synthetic demand has a strong, learnable weekly and holiday structure.
    assert demand["overall"]["model"]["mape"] < 5


def test_training_is_deterministic(trained: TrainResult) -> None:
    again = train(make_history(days=560), FAST, SMALL, TARGETS)
    assert again.metrics["targets"] == trained.metrics["targets"]
    assert again.run_id.split("-")[1] == trained.run_id.split("-")[1]


def test_forecasts_are_ordered_positive_and_explained(trained: TrainResult) -> None:
    history = make_history(days=560)
    for model in trained.models.values():
        out = forecast_target(history, model)
        assert len(out) == model.spec.horizon
        assert (out["p10"] > 0).all()
        assert (out["p10"] <= out["p50"]).all()
        assert (out["p50"] <= out["p90"]).all()
        assert out["day"].iloc[0] == history.index[-1] + pd.Timedelta(days=1)
        assert out["horizon"].tolist() == model.spec.horizons
        assert all(len(d) == 5 for d in out["drivers"])


def test_model_store_round_trip(trained: TrainResult, tmp_path: Path) -> None:
    store = tmp_path
    save_models(store, trained)
    run_id, models = load_models(store)
    assert run_id == trained.run_id
    history = make_history(days=560)
    for name, model in trained.models.items():
        a = forecast_target(history, model)
        b = forecast_target(history, models[name])
        np.testing.assert_allclose(a[["p10", "p50", "p90"]], b[["p10", "p50", "p90"]])
    with pytest.raises(FileNotFoundError):
        load_models(store / "empty")


def test_origins_move_back_to_an_observed_day(history: pd.DataFrame) -> None:
    gappy = history.copy()
    gappy.loc["2024-05-09":"2024-05-10", "price_mean_cop_kwh"] = np.nan
    targets = ["demand_kwh", "price_mean_cop_kwh"]
    assert observed_origin(gappy, targets, pd.Timestamp("2024-05-10")) == pd.Timestamp("2024-05-08")
    assert observed_origin(gappy, targets, pd.Timestamp("2024-05-11")) == pd.Timestamp("2024-05-11")
    gappy.loc["2024-04-01":"2024-04-08", "demand_kwh"] = np.nan
    with pytest.raises(ValueError, match="no observed"):
        observed_origin(gappy, targets, pd.Timestamp("2024-04-08"))


def test_last_reference_survives_a_sparse_week(history: pd.DataFrame) -> None:
    sparse = history.copy()
    sparse.loc["2024-06-08":"2024-06-11", "price_mean_cop_kwh"] = np.nan
    model = ModelConfig(reference="last")
    feats = build_features(sparse, pd.Timestamp("2024-06-12"), [1, 2], "price_mean_cop_kwh")
    assert feats["ref_log"].isna().all()  # fewer than 5 of 7 days observed
    offset = reference_offset(feats, model.reference)
    assert np.allclose(offset, np.log(sparse.loc["2024-06-12", "price_mean_cop_kwh"]))
