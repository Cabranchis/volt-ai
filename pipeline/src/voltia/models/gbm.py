"""LightGBM quantile regressors, one booster per quantile, trained on log-ratio targets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import lightgbm as lgb
import numpy as np

QUANTILES = (0.1, 0.5, 0.9)


@dataclass(frozen=True)
class GBMParams:
    """Hyperparameters, fixed before the reported backtest (see docs/model-card.md)."""

    num_boost_round: int = 400
    learning_rate: float = 0.04
    num_leaves: int = 15
    min_data_in_leaf: int = 100
    bagging_fraction: float = 0.7
    feature_fraction: float = 0.8
    lambda_l2: float = 1.0
    max_bin: int = 127
    seed: int = 20261024
    num_threads: int = 2

    def lgb_params(self, alpha: float) -> dict[str, Any]:
        params = asdict(self)
        params.pop("num_boost_round")
        params.update(
            {
                "objective": "quantile",
                "alpha": alpha,
                "bagging_freq": 1,
                "deterministic": True,
                "force_row_wise": True,
                "verbosity": -1,
            }
        )
        return params


def fit_quantiles(
    x: np.ndarray,
    z: np.ndarray,
    params: GBMParams,
    feature_names: list[str],
    quantiles: tuple[float, ...] = QUANTILES,
) -> list[lgb.Booster]:
    """Fit one booster per quantile on features x and the transformed target z."""
    data = lgb.Dataset(
        np.asarray(x, dtype=np.float32), label=z, feature_name=feature_names, free_raw_data=False
    )
    return [
        lgb.train(params.lgb_params(q), data, num_boost_round=params.num_boost_round)
        for q in quantiles
    ]


def predict_quantiles(boosters: list[lgb.Booster], x: np.ndarray) -> np.ndarray:
    """Predictions (n, len(boosters)), sorted per row so the quantiles never cross."""
    data = np.asarray(x, dtype=np.float32)
    raw = np.column_stack([np.asarray(b.predict(data), dtype=float) for b in boosters])
    return np.sort(raw, axis=1)
