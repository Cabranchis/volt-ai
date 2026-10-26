"""Quantile model families behind one function: fit on (x, z), predict three quantiles of z.

Every family returns an array (n, 3) for the 0.1, 0.5 and 0.9 quantiles. Tree libraries that
accept NaN get the raw matrix; the others get training-median imputation. Seeds are fixed.
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np

from voltia.models.gbm import GBMParams, fit_quantiles, predict_quantiles

QS = (0.1, 0.5, 0.9)
THREADS = 6
SEED = 20261024


def _impute(x_train: np.ndarray, x_pred: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    med = np.nanmedian(x_train, axis=0)
    med = np.where(np.isnan(med), 0.0, med)
    a = np.where(np.isnan(x_train), med, x_train)
    b = np.where(np.isnan(x_pred), med, x_pred)
    return a, b


def lightgbm(x: np.ndarray, z: np.ndarray, xp: np.ndarray, names: list[str], **opt: Any) -> np.ndarray:
    weight = opt.pop("sample_weight", None)
    params = GBMParams(num_threads=THREADS, **opt)
    if weight is None:
        return predict_quantiles(fit_quantiles(x, z, params, names), xp)
    import lightgbm as lgb

    data = lgb.Dataset(np.asarray(x, dtype=np.float32), label=z, weight=weight, feature_name=names)
    boosters = [lgb.train(params.lgb_params(q), data, num_boost_round=params.num_boost_round) for q in QS]
    return predict_quantiles(boosters, xp)


def xgboost(x: np.ndarray, z: np.ndarray, xp: np.ndarray, names: list[str], **opt: Any) -> np.ndarray:
    import xgboost as xgb

    weight = opt.pop("sample_weight", None)
    params = {
        "n_estimators": 400,
        "learning_rate": 0.04,
        "max_depth": 4,
        "min_child_weight": 50,
        "subsample": 0.7,
        "colsample_bytree": 0.8,
        "reg_lambda": 1.0,
        **opt,
    }
    model = xgb.XGBRegressor(
        objective="reg:quantileerror",
        quantile_alpha=np.array(QS),
        tree_method="hist",
        n_jobs=THREADS,
        random_state=SEED,
        **params,
    )
    model.fit(np.asarray(x, dtype=np.float32), z, sample_weight=weight)
    return np.sort(np.asarray(model.predict(np.asarray(xp, dtype=np.float32))), axis=1)


def catboost(x: np.ndarray, z: np.ndarray, xp: np.ndarray, names: list[str], **opt: Any) -> np.ndarray:
    from catboost import CatBoostRegressor

    params = {"iterations": 500, "learning_rate": 0.05, "depth": 5, "l2_leaf_reg": 3.0, **opt}
    model = CatBoostRegressor(
        loss_function="MultiQuantile:alpha=0.1,0.5,0.9",
        random_seed=SEED,
        thread_count=THREADS,
        verbose=False,
        **params,
    )
    model.fit(np.asarray(x, dtype=np.float64), z)
    return np.sort(np.asarray(model.predict(np.asarray(xp, dtype=np.float64))), axis=1)


def quantile_forest(x: np.ndarray, z: np.ndarray, xp: np.ndarray, names: list[str], **opt: Any) -> np.ndarray:
    from quantile_forest import ExtraTreesQuantileRegressor

    a, b = _impute(x, xp)
    params = {"n_estimators": 200, "min_samples_leaf": 60, "max_features": 0.5, **opt}
    model = ExtraTreesQuantileRegressor(n_jobs=THREADS, random_state=SEED, **params)
    model.fit(a, z)
    return np.sort(np.asarray(model.predict(b, quantiles=list(QS))), axis=1)


def linear_quantile(x: np.ndarray, z: np.ndarray, xp: np.ndarray, names: list[str], **opt: Any) -> np.ndarray:
    """Ridge on z for the median; the 0.1 and 0.9 quantiles add the in-sample residual quantiles.

    Exact linear quantile regression (HiGHS) took minutes per origin on this many rows, so the
    spread comes from the pooled residuals of all horizons instead (the online calibration
    later widens it per horizon bucket).
    """
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    a, b = _impute(x, xp)
    scaler = StandardScaler().fit(a)
    a, b = scaler.transform(a), scaler.transform(b)
    model = Ridge(alpha=opt.get("alpha", 10.0)).fit(a, z)
    resid = z - model.predict(a)
    lo, hi = np.quantile(resid, [QS[0], QS[2]])
    mid = model.predict(b)
    return np.column_stack([mid + lo, mid, mid + hi])


FAMILIES = {
    "lightgbm": lightgbm,
    "xgboost": xgboost,
    "catboost": catboost,
    "quantile_forest": quantile_forest,
    "linear_quantile": linear_quantile,
}


def fit_predict(
    family: str, x: np.ndarray, z: np.ndarray, xp: np.ndarray, names: list[str], **opt: Any
) -> np.ndarray:
    return FAMILIES[family](x, z, xp, names, **opt)
