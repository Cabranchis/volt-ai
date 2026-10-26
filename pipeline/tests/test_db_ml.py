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


def _log(engine: Engine) -> pd.DataFrame:
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT target, origin, day, horizon, run_id, p50 FROM forecast_log ORDER BY day"
        ).all()
    return pd.DataFrame(rows, columns=["target", "origin", "day", "horizon", "run_id", "p50"])


def test_forecast_log_survives_pruning_and_is_never_revised(engine: Engine) -> None:
    for i in range(3):
        _run(engine, f"r{i}", minutes=i)
        frame = _forecasts(days=2, start=f"2026-10-{22 + i}")  # the origin moves one day per run
        frame["p50"], frame["p90"] = 2.0 + i, 3.0 + i
        db.upsert_forecasts(engine, f"r{i}", frame, keep_runs=1)
    with engine.connect() as conn:
        kept = {r[0] for r in conn.exec_driver_sql("SELECT DISTINCT run_id FROM forecasts")}
    assert kept == {"r2"}
    log = _log(engine)
    assert len(log) == 6  # three origins, two days each
    assert sorted({str(d) for d in log["origin"]}) == ["2026-10-21", "2026-10-22", "2026-10-23"]
    assert set(log["run_id"]) == {"r0", "r1", "r2"}
    first = log[(log["run_id"] == "r0")]
    assert first["p50"].tolist() == [2.0, 2.0]

    # the same origin issued again later does not replace what was logged first
    _run(engine, "r9", minutes=9)
    again = _forecasts(days=2, start="2026-10-22")
    again["p50"], again["p90"] = 9.0, 10.0
    db.upsert_forecasts(engine, "r9", again, keep_runs=1)
    after = _log(engine)
    assert len(after) == 6
    assert 9.0 not in after["p50"].tolist()


def test_archiving_with_no_forecasts_is_a_no_op(engine: Engine) -> None:
    with engine.begin() as conn:
        assert db.archive_forecasts(conn) == 0


def test_weather_forecast_log_keeps_the_first_issue_of_a_day(engine: Engine) -> None:
    frame = pd.DataFrame(
        {
            "issued": pd.Timestamp("2026-10-26"),
            "location": ["chivor", "chivor"],
            "day": pd.to_datetime(["2026-10-26", "2026-10-27"]),
            "lead_days": [0, 1],
            "precip_mm": [3.0, 8.0],
            "temp_c": [17.0, 16.0],
            "model": "gfs_seamless",
        }
    )
    assert db.archive_weather_forecast(engine, frame) == 2
    revised = frame.assign(precip_mm=[99.0, 99.0])
    assert db.archive_weather_forecast(engine, revised) == 0  # never rewritten
    # a later run of the same date cannot add rows the first one did not have
    extra = frame.assign(location="betania")
    assert db.archive_weather_forecast(engine, extra) == 0
    with engine.connect() as conn:
        stored = [
            r[0]
            for r in conn.exec_driver_sql("SELECT precip_mm FROM weather_forecast_log ORDER BY day")
        ]
    assert stored == [3.0, 8.0]
    with engine.connect() as conn:
        assert (
            conn.exec_driver_sql(
                "SELECT COUNT(*) FROM weather_forecast_log WHERE fetched_at IS NULL"
            ).scalar()
            == 0
        )
    later = frame.assign(issued=pd.Timestamp("2026-10-27"), precip_mm=[5.0, 6.0])
    assert db.archive_weather_forecast(engine, later) == 2  # a new issue date adds its own rows
