"""The publication gate: checks that run before a model or a forecast is stored for the site.

A forecast that is stored is shown to people who decide with it, and `forecast_log` keeps it for
good, so a bad run must not get that far. Each check returns the problems it found as plain
sentences; `enforce` raises `GateError` when there are any (mode "enforce"), only logs them (mode
"warn", for a person who has looked at the problems and decided to publish anyway) or skips the
checks ("off", for the unit tests of the commands). When the gate stops a run nothing is written,
so the site keeps the previous forecast and its age.

Thresholds are measured, not guessed: the production backtest has 51 test dates, the calibrated
coverage of the 80 % range was 0.82 for demand and 0.81 for price, and the model beats the weekly
seasonal naive with a MASE 32 % (demand) and 42 % (price) lower. The limits below leave room for a
bad month and still catch a model that is broken.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import structlog

from voltia.features import TARGETS
from voltia.schemas import DAILY_BOUNDS

log = structlog.get_logger()


class GateError(RuntimeError):
    """The run is not published; the message lists every rule that failed."""


@dataclass(frozen=True)
class GateLimits:
    min_origins: int = 40  # production backtest: 51 test dates
    coverage_low: float = 0.60  # calibrated coverage of the nominal 0.80 range (measured 0.81-0.82)
    coverage_high: float = 0.95
    max_data_age_days: int = 10  # XM publishes the complete price about 3 days late
    max_oni_age_days: int = 150  # the ONI is monthly and arrives about 75 days late
    max_weather_age_days: int = 30  # rain and temperature missing make their features unknown (NaN)
    band_window_days: int = 90  # recent history the price forecast is compared with
    band_low: float = 0.5  # the P50 may not leave [0.5 x lowest, 1.5 x highest] of that window
    band_high: float = 1.5


DEFAULT_LIMITS = GateLimits()


def check_metrics(metrics: dict[str, Any], limits: GateLimits = DEFAULT_LIMITS) -> list[str]:
    """Backtest of a new run: enough test dates, a calibrated range and better than the naive."""
    problems: list[str] = []
    for target, m in metrics.get("targets", {}).items():
        overall = m["overall"]
        model, naive = overall["model"]["mase"], overall["seasonal_naive"]["mase"]
        if not (np.isfinite(model) and np.isfinite(naive)):
            problems.append(f"{target}: the backtest error is not a number")
        elif model > naive:
            problems.append(
                f"{target}: the model is worse than the weekly seasonal naive "
                f"(MASE {model:.2f} against {naive:.2f})"
            )
        if m["n_origins"] < limits.min_origins:
            problems.append(
                f"{target}: only {m['n_origins']} test dates (at least {limits.min_origins})"
            )
        calibrated = m["coverage"]["calibrated"]
        if calibrated is not None and not limits.coverage_low <= calibrated <= limits.coverage_high:
            problems.append(
                f"{target}: the 80 % range covers {calibrated:.2f} of the test days "
                f"(expected {limits.coverage_low:.2f} to {limits.coverage_high:.2f})"
            )
    return problems


def check_forecasts(
    frame: pd.DataFrame, history: pd.DataFrame, limits: GateLimits = DEFAULT_LIMITS
) -> list[str]:
    """The forecast rows: finite, ordered, the right length and not far from recent history."""
    problems: list[str] = []
    for target, spec in TARGETS.items():
        part = frame[frame["target"] == target]
        if part.empty:
            problems.append(f"{target}: no forecast rows")
            continue
        values = part[["p10", "p50", "p90"]].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            problems.append(f"{target}: the forecast has values that are not numbers")
            continue
        if len(part) != spec.horizon:
            problems.append(f"{target}: {len(part)} forecast days instead of {spec.horizon}")
        if not ((part["p10"] <= part["p50"]) & (part["p50"] <= part["p90"])).all():
            problems.append(f"{target}: P10, P50 and P90 are not in order")
        low, high = _plausible_band(target, history, limits)
        outside = part[(part["p50"] < low) | (part["p50"] > high)]
        if not outside.empty:
            row = outside.iloc[0]
            problems.append(
                f"{target}: the central forecast of {pd.Timestamp(row['day']).date()} "
                f"({row['p50']:.4g}) is outside {low:.4g} to {high:.4g}"
            )
    return problems


def _plausible_band(target: str, history: pd.DataFrame, limits: GateLimits) -> tuple[float, float]:
    """Where the central forecast of `target` may lie.

    The price is compared with its own recent range, because a price forecast that is far outside
    what the market did in the last 90 days is far more likely a defect than news. The demand has
    a narrow plausible range in absolute terms (`DAILY_BOUNDS`).
    """
    if target == "price_mean_cop_kwh":
        recent = history[target].dropna().iloc[-limits.band_window_days :]
        if len(recent) >= 30:
            return float(recent.min()) * limits.band_low, float(recent.max()) * limits.band_high
    return DAILY_BOUNDS[target]


def check_freshness(
    history: pd.DataFrame, today: date, limits: GateLimits = DEFAULT_LIMITS
) -> list[str]:
    """The data the forecast starts from is recent: the targets, the ONI and the weather."""
    problems: list[str] = []
    wanted = [(t, limits.max_data_age_days) for t in TARGETS]
    wanted += [("oni", limits.max_oni_age_days), ("weather_temp_c", limits.max_weather_age_days)]
    for series, max_age in wanted:
        newest = history[series].last_valid_index() if series in history.columns else None
        if newest is None:
            problems.append(f"{series}: no data")
            continue
        age = (pd.Timestamp(today) - pd.Timestamp(str(newest))).days
        if age > max_age:
            problems.append(f"{series}: the newest day is {age} days old (at most {max_age})")
    return problems


def enforce(problems: list[str], mode: str) -> None:
    """Stop the run when there are problems, unless the mode says to publish anyway."""
    if not problems or mode == "off":
        return
    for problem in problems:
        log.error("gate.failed", problem=problem, mode=mode)
    if mode == "warn":
        log.warning("gate.published_anyway", problems=len(problems))
        return
    raise GateError("not published: " + "; ".join(problems))
