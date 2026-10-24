from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from voltia import db


def _run(engine: Engine, run_id: str, minutes: int = 0) -> None:
    db.insert_model_run(
        engine,
        run_id,
        datetime(2026, 10, 24, 12, 0, tzinfo=UTC).replace(tzinfo=None) + timedelta(minutes=minutes),
        date(2018, 1, 1),
        date(2026, 10, 21),
        {"mase": 0.7, "bad": float("nan")},
        {"seed": 1},
    )


def _forecasts(
    target: str = "demand_kwh", days: int = 3, start: str = "2026-10-22"
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "target": target,
            "day": pd.date_range(start, periods=days),
            "horizon": np.arange(1, days + 1),
            "p10": 1.0,
            "p50": 2.0,
            "p90": 3.0,
            "drivers": [[{"feature": "h", "contribution": 0.5, "direction": "up"}]] * days,
        }
    )


def test_model_run_is_idempotent_and_json_safe(engine: Engine) -> None:
    _run(engine, "r1")
    _run(engine, "r1")
    assert db.table_counts(engine, ["model_runs"]) == {"model_runs": 1}
    assert db.run_exists(engine, "r1")
    assert not db.run_exists(engine, "nope")
    with engine.connect() as conn:
        metrics = conn.exec_driver_sql("SELECT metrics FROM model_runs").scalar_one()
    assert '"bad": null' in metrics


def test_forecasts_are_replaced_per_run_and_target(engine: Engine) -> None:
    _run(engine, "r1")
    db.upsert_forecasts(engine, "r1", _forecasts(days=3))
    db.upsert_forecasts(engine, "r1", _forecasts(days=3))
    assert db.table_counts(engine, ["forecasts"]) == {"forecasts": 3}
    # A later origin: the old rows of that run and target are replaced, not mixed.
    db.upsert_forecasts(engine, "r1", _forecasts(days=2, start="2026-10-23"))
    with engine.connect() as conn:
        days = [r[0] for r in conn.exec_driver_sql("SELECT day FROM forecasts ORDER BY day")]
    assert [str(d) for d in days] == ["2026-10-23", "2026-10-24"]
    db.upsert_forecasts(engine, "r1", _forecasts("price_mean_cop_kwh", days=2))
    assert db.table_counts(engine, ["forecasts"]) == {"forecasts": 4}


def test_only_recent_runs_keep_forecasts(engine: Engine) -> None:
    for i in range(4):
        _run(engine, f"r{i}", minutes=i)
        db.upsert_forecasts(engine, f"r{i}", _forecasts(), keep_runs=2)
    with engine.connect() as conn:
        runs = {r[0] for r in conn.exec_driver_sql("SELECT DISTINCT run_id FROM forecasts")}
    assert runs == {"r2", "r3"}
    assert db.table_counts(engine, ["model_runs"]) == {"model_runs": 4}


def test_anomalies_are_replaced_per_target(engine: Engine) -> None:
    frame = pd.DataFrame(
        {
            "target": "demand_kwh",
            "day": pd.to_datetime(["2020-03-25", "2020-03-26"]),
            "severity": [5.0, 4.0],
            "direction": ["low", "low"],
            "method": "m",
            "detail": [{"z": -6.0}, {"z": -5.0}],
        }
    )
    db.upsert_anomalies(engine, frame)
    db.upsert_anomalies(engine, frame)
    assert db.table_counts(engine, ["anomalies"]) == {"anomalies": 2}
    db.upsert_anomalies(engine, frame.iloc[:1])
    assert db.table_counts(engine, ["anomalies"]) == {"anomalies": 1}
    db.upsert_anomalies(engine, frame.iloc[:0], targets=["demand_kwh"])
    assert db.table_counts(engine, ["anomalies"]) == {"anomalies": 0}


def test_json_safe_handles_nested_values() -> None:
    value = {"a": [1.0, float("inf"), {"b": float("nan")}], "c": (1, 2), 3: "x"}
    assert db.json_safe(value) == {"a": [1.0, None, {"b": None}], "c": [1, 2], "3": "x"}


def test_negative_severity_is_rejected(engine: Engine) -> None:
    bad = pd.DataFrame(
        {
            "target": ["x"],
            "day": pd.to_datetime(["2020-01-01"]),
            "severity": [-1.0],
            "direction": ["low"],
            "method": ["m"],
            "detail": [None],
        }
    )
    with pytest.raises(IntegrityError):
        db.upsert_anomalies(engine, bad)


def test_postgres_engine_survives_idle_connections() -> None:
    """Neon drops idle connections; the pool must check before reuse (nothing connects)."""
    engine = db.make_engine("postgresql+psycopg://u:p@localhost:1/x")
    assert engine.pool._pre_ping is True
    assert engine.pool._recycle == 240
