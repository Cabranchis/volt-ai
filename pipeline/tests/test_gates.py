"""The publication gate: a bad run is refused and nothing is stored."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from conftest import make_history
from voltia import db
from voltia.cli import app
from voltia.config import get_settings
from voltia.gates import (
    GateError,
    GateLimits,
    check_forecasts,
    check_freshness,
    check_metrics,
    enforce,
)

runner = CliRunner()
TODAY = date(2026, 11, 15)
TRAIN = ["train", "--predict", "--origins", "2", "--warmup", "1", "--step", "20", "--rounds", "15"]


def _metrics(
    model: float = 0.8, naive: float = 1.0, origins: int = 51, coverage: float | None = 0.85
) -> dict[str, Any]:
    target = {
        "n_origins": origins,
        "overall": {"model": {"mase": model}, "seasonal_naive": {"mase": naive}},
        "coverage": {"calibrated": coverage},
    }
    return {"targets": {"demand_kwh": target, "price_mean_cop_kwh": target}}


def _history(end: str = "2026-11-11", days: int = 200) -> pd.DataFrame:
    index = pd.date_range(end=end, periods=days)
    return pd.DataFrame(
        {
            "demand_kwh": 2.4e8,
            "price_mean_cop_kwh": np.linspace(400.0, 600.0, days),
            "oni": 1.0,
            "weather_temp_c": 20.0,
        },
        index=index,
    )


def _frame(price_p50: float = 500.0, demand_p50: float = 2.4e8) -> pd.DataFrame:
    rows = []
    for target, horizon, p50 in (
        ("demand_kwh", 30, demand_p50),
        ("price_mean_cop_kwh", 14, price_p50),
    ):
        for h in range(1, horizon + 1):
            day = pd.Timestamp("2026-11-12") + pd.Timedelta(days=h - 1)
            rows.append(
                {"target": target, "day": day, "p10": p50 * 0.9, "p50": p50, "p90": p50 * 1.1}
            )
    return pd.DataFrame(rows)


def test_a_healthy_run_passes_every_check() -> None:
    assert check_metrics(_metrics()) == []
    assert check_freshness(_history(), TODAY) == []
    assert check_forecasts(_frame(), _history()) == []


def test_a_model_worse_than_the_naive_is_refused() -> None:
    problems = check_metrics(_metrics(model=1.2, naive=1.0))
    assert any("worse than the weekly seasonal naive" in p for p in problems)


def test_too_few_test_dates_or_a_miscalibrated_range_is_refused() -> None:
    assert any("only 12 test dates" in p for p in check_metrics(_metrics(origins=12)))
    assert any("covers 0.42" in p for p in check_metrics(_metrics(coverage=0.42)))
    assert any("covers 0.99" in p for p in check_metrics(_metrics(coverage=0.99)))
    assert check_metrics(_metrics(coverage=None)) == []  # uncalibrated: nothing to judge


def test_a_nan_backtest_is_refused() -> None:
    assert any("not a number" in p for p in check_metrics(_metrics(model=float("nan"))))


def test_forecast_rows_must_be_finite_ordered_and_complete() -> None:
    frame = _frame()
    frame.loc[0, "p50"] = np.nan
    assert any("not numbers" in p for p in check_forecasts(frame, _history()))
    frame = _frame()
    frame.loc[frame["target"] == "price_mean_cop_kwh", "p10"] = 900.0
    assert any("not in order" in p for p in check_forecasts(frame, _history()))
    short = _frame().iloc[:-3]
    assert any("instead of" in p for p in check_forecasts(short, _history()))
    assert any("no forecast rows" in p for p in check_forecasts(_frame().iloc[:30], _history()))


def test_a_price_far_from_recent_history_is_refused() -> None:
    # The last 90 days ran from about 500 to 600: 1.5 x the highest is about 900.
    problems = check_forecasts(_frame(price_p50=5.0), _history())
    assert any("price_mean_cop_kwh" in p and "outside" in p for p in problems)
    assert any("outside" in p for p in check_forecasts(_frame(price_p50=9000.0), _history()))
    assert check_forecasts(_frame(price_p50=850.0), _history()) == []  # a real spike is allowed


def test_a_demand_outside_the_physical_range_is_refused() -> None:
    assert any("demand_kwh" in p for p in check_forecasts(_frame(demand_p50=2.4e5), _history()))


def test_stale_inputs_are_refused() -> None:
    problems = check_freshness(_history(end="2026-10-20"), TODAY)
    assert any("demand_kwh" in p and "days old" in p for p in problems)
    stale_oni = _history()
    stale_oni["oni"] = stale_oni["oni"].where(stale_oni.index < "2026-05-01")
    assert any("oni" in p for p in check_freshness(stale_oni, TODAY))
    assert any("no data" in p for p in check_freshness(_history().drop(columns="oni"), TODAY))


def test_limits_can_be_widened_by_a_person_who_decided_to() -> None:
    wide = GateLimits(max_data_age_days=60, max_weather_age_days=60)
    assert check_freshness(_history(end="2026-10-20"), TODAY, wide) == []


def test_enforce_modes() -> None:
    with pytest.raises(GateError, match="not published: a; b"):
        enforce(["a", "b"], "enforce")
    enforce(["a"], "warn")  # logged and published
    enforce(["a"], "off")
    enforce([], "enforce")


@pytest.fixture
def stale_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A database whose history is years old, as if the pipeline had stopped ingesting."""
    path = tmp_path / "gate.sqlite"
    monkeypatch.setenv("VOLTIA_LOCAL_DB", str(path))
    monkeypatch.setenv("VOLTIA_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("VOLTIA_GATE_MODE", raising=False)
    get_settings.cache_clear()
    engine = db.make_engine(f"sqlite:///{path.as_posix()}")
    db.migrate(engine)
    wide = make_history(days=500)
    long = wide.reset_index().melt(id_vars="day", var_name="series").dropna()
    db.upsert_series_daily(engine, long)
    return path


def test_the_command_refuses_stale_data_and_stores_nothing(stale_db: Path) -> None:
    result = runner.invoke(app, TRAIN)
    assert result.exit_code == 1, result.output
    assert "publication gate" in result.output
    assert "days old" in result.output  # refused for the stale data, not only for the tiny backtest
    engine = db.make_engine(f"sqlite:///{stale_db.as_posix()}")
    assert db.table_counts(engine, ["model_runs", "forecasts"]) == {"model_runs": 0, "forecasts": 0}
    assert not (stale_db.parent / "models").exists()


def test_warn_mode_publishes_after_a_person_decided(
    stale_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VOLTIA_GATE_MODE", "warn")
    get_settings.cache_clear()
    result = runner.invoke(app, TRAIN)
    assert result.exit_code == 0, result.output
    engine = db.make_engine(f"sqlite:///{stale_db.as_posix()}")
    assert db.table_counts(engine, ["model_runs"])["model_runs"] == 1
