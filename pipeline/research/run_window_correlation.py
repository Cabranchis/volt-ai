"""Does a correlation between days that fades with distance improve the cost calculator's range?

The calculator (web/src/lib/cost.ts) gives every pair of days in a window the same correlation, 0.7,
chosen by run_cost_window.py on the 51 production dates. This script asks whether the real structure
is different and whether using it gives a better range for the mean price of a window.

Data: the 151 dense dates of results/dense_backtest.json (no database, no network). The errors of
each day are standardised with the day's own calibrated band, z = (log y - log P50) / sigma, where
sigma = (log P90 - log P10) / (2 * 1.2816), exactly as the calculator reads a band.

Design, fixed before the first run: the structure is fitted on the first half of the dates (75) and
judged on the second half (76), so it is never judged on what it was fitted on. Candidates: the
current equal correlation 0.7; AR(1), rho(lag) = phi^lag; and a common factor plus AR(1),
rho(lag) = r0 + (1 - r0) * phi^lag. Each window (3, 7 and 12 days, starting at horizon 3, as the
calculator does) is simulated with the Cholesky factor L of its correlation matrix (S = L L^T) and
scored on the second half by the coverage of the P10-P90 range, the share of misses below P10, the
mean relative width and the mean pinball loss of P10, P50 and P90.

Decision rule: the new structure replaces 0.7 only if, on the second half, its mean absolute distance
of the coverage from 0.80 over the three lengths is smaller AND its mean pinball is not larger at any
length. Otherwise 0.7 stays.

    uv run python research/run_window_correlation.py

Writes research/results/window_correlation.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

HERE = Path(__file__).parent
SOURCE = HERE / "results" / "dense_backtest.json"
OUT = HERE / "results" / "window_correlation.json"
Z90 = 1.2815515655446004
START = 3
LENGTHS = (3, 7, 12)
LAGS = np.arange(1, 12)
DRAWS = 4000
CURRENT_RHO = 0.7


def load() -> pd.DataFrame:
    rows = pd.DataFrame(json.loads(SOURCE.read_text()))
    rows = rows[rows["y"].notna()].copy()
    rows["sigma"] = np.maximum((np.log(rows["m90"]) - np.log(rows["m10"])) / (2 * Z90), 1e-3)
    rows["z"] = (np.log(rows["y"]) - np.log(rows["m50"])) / rows["sigma"]
    return rows


def lag_correlation(wide: pd.DataFrame) -> np.ndarray:
    """Pooled correlation of the standardised errors of two days `lag` apart, for lag 1 to 11."""
    variance = np.nanmean(wide.to_numpy() ** 2)
    out = []
    for lag in LAGS:
        products = [(wide[h] * wide[h + lag]).dropna().to_numpy() for h in wide.columns if h + lag in wide.columns]
        out.append(np.concatenate(products).mean() / variance)
    return np.array(out)


def fit(kind: str, empirical: np.ndarray) -> np.ndarray:
    if kind == "ar1":
        return least_squares(lambda p: p[0] ** LAGS - empirical, [0.8], bounds=([0.0], [0.999])).x
    return least_squares(
        lambda p: p[0] + (1 - p[0]) * p[1] ** LAGS - empirical, [0.4, 0.8], bounds=([0.0, 0.0], [1.0, 0.999])
    ).x


def correlation(kind: str, params: np.ndarray, lag: int) -> float:
    if lag == 0:
        return 1.0
    if kind == "equal":
        return float(params[0])
    if kind == "ar1":
        return float(params[0] ** lag)
    return float(params[0] + (1 - params[0]) * params[1] ** lag)


def cholesky(kind: str, params: np.ndarray, n: int) -> np.ndarray:
    matrix = np.array([[correlation(kind, params, abs(i - j)) for j in range(n)] for i in range(n)])
    return np.linalg.cholesky(matrix + 1e-9 * np.eye(n))


def pinball(y: float, q: float, alpha: float) -> float:
    d = y - q
    return float(max(alpha * d, (alpha - 1) * d))


def evaluate(rows: pd.DataFrame, origins: list[str], kind: str, params: np.ndarray, length: int) -> dict[str, float]:
    rng = np.random.default_rng(5)
    factor = cholesky(kind, params, length)
    inside, below, widths, losses = [], [], [], []
    for origin in origins:
        part = rows[(rows["origin"] == origin) & rows["h"].isin(range(START, START + length))].sort_values("h")
        if len(part) != length:
            continue
        mu, sigma = np.log(part["m50"].to_numpy()), part["sigma"].to_numpy()
        z = rng.standard_normal((DRAWS, length)) @ factor.T
        mean = np.exp(mu + sigma * z).mean(axis=1)
        p10, p50, p90 = (float(v) for v in np.percentile(mean, [10, 50, 90]))
        actual = float(part["y"].mean())
        inside.append(p10 <= actual <= p90)
        below.append(actual < p10)
        widths.append((p90 - p10) / p50)
        losses.append(np.mean([pinball(actual, p10, 0.1), pinball(actual, p50, 0.5), pinball(actual, p90, 0.9)]))
    return {
        "dates": len(inside),
        "coverage": round(float(np.mean(inside)), 3),
        "share_below_p10": round(float(np.mean(below)), 3),
        "mean_relative_width": round(float(np.mean(widths)), 3),
        "pinball": round(float(np.mean(losses)), 3),
    }


def main() -> None:
    rows = load()
    origins = sorted(rows["origin"].unique())
    train, test = origins[: len(origins) // 2], origins[len(origins) // 2 :]
    wide = rows[rows["h"] >= START].pivot(index="origin", columns="h", values="z")
    empirical = {"first half": lag_correlation(wide.loc[train]), "second half": lag_correlation(wide.loc[test])}
    fitted = {
        "equal_0.7": ("equal", np.array([CURRENT_RHO])),
        "ar1": ("ar1", fit("ar1", empirical["first half"])),
        "factor_ar1": ("factor", fit("factor", empirical["first half"])),
    }
    out: dict[str, object] = {
        "train_dates": len(train),
        "test_dates": len(test),
        "lag_correlation": {k: [round(float(x), 3) for x in v] for k, v in empirical.items()},
        "parameters": {k: [round(float(x), 3) for x in p] for k, (_, p) in fitted.items()},
        "second_half": {},
    }
    summary: dict[str, dict[str, float]] = {}
    for name, (kind, params) in fitted.items():
        per_length = {str(n): evaluate(rows, test, kind, params, n) for n in LENGTHS}
        out["second_half"][name] = per_length  # type: ignore[index]
        summary[name] = {
            "coverage_distance": float(np.mean([abs(per_length[str(n)]["coverage"] - 0.8) for n in LENGTHS])),
            "pinball": {str(n): per_length[str(n)]["pinball"] for n in LENGTHS},  # type: ignore[dict-item]
        }
    base = summary["equal_0.7"]
    for name in ("ar1", "factor_ar1"):
        s = summary[name]
        better_coverage = s["coverage_distance"] < base["coverage_distance"]
        pinball_ok = all(s["pinball"][str(n)] <= base["pinball"][str(n)] for n in LENGTHS)  # type: ignore[index]
        s["replaces_equal"] = bool(better_coverage and pinball_ok)  # type: ignore[assignment]
    out["decision"] = summary
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("lag correlation, first half :", np.round(empirical["first half"], 2))
    print("lag correlation, second half:", np.round(empirical["second half"], 2))
    for name, (_, params) in fitted.items():
        print(f"\n{name} {np.round(params, 3)}")
        for n in LENGTHS:
            print(f"  {n:>2} days", out["second_half"][name][str(n)])  # type: ignore[index]
    print("\ndecision:", json.dumps({k: v.get("replaces_equal") for k, v in summary.items()}))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
