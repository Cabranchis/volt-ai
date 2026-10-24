"""Forecast explanations with SHAP (requirement FR-08).

The P50 booster predicts log(y) minus a reference, so SHAP values are additive in log units.
A driver's contribution in target units is how much the forecast would change if that
feature's SHAP term were removed: forecast * (1 - exp(-phi)). It keeps the sign of phi and is
exact for each feature on its own; contributions of several features do not add up exactly.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import shap

LABELS_PATH = Path(__file__).with_name("feature_labels.json")
TOP_K = 5


def shap_values(booster: Any, x: np.ndarray) -> np.ndarray:
    """SHAP values (n, n_features) of a LightGBM booster's raw output."""
    values = shap.TreeExplainer(booster).shap_values(np.asarray(x, dtype=np.float32))
    return np.asarray(values, dtype=float)


def top_drivers(
    phi: np.ndarray, forecast: np.ndarray, features: list[str], k: int = TOP_K
) -> list[list[dict[str, Any]]]:
    """Top k drivers per row as dicts with feature, contribution (target units), direction."""
    out: list[list[dict[str, Any]]] = []
    for row_phi, value in zip(phi, forecast, strict=True):
        order = np.argsort(-np.abs(row_phi), kind="stable")[:k]
        out.append(
            [
                {
                    "feature": features[i],
                    "contribution": float(value * (1 - np.exp(-row_phi[i]))),
                    "direction": "up" if row_phi[i] > 0 else "down",
                }
                for i in order
            ]
        )
    return out


@lru_cache(maxsize=1)
def feature_labels() -> dict[str, dict[str, str]]:
    """Plain-language names per feature key, in Spanish and English."""
    data: dict[str, dict[str, str]] = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    return data
