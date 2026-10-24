from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from voltia import db


def _frame(
    values: list[float], series: str = "demand_kwh", start: str = "2026-10-01"
) -> pd.DataFrame:
    return pd.DataFrame(
        {"series": series, "day": pd.date_range(start, periods=len(values)), "value": values}
    )


def test_migrate_creates_tables_and_is_idempotent(tmp_path: Path) -> None:
    engine = db.make_engine(f"sqlite:///{(tmp_path / 'm.sqlite').as_posix()}")
    first = db.migrate(engine)
    assert first == ["0001_init"]  # the .pg.sql file is skipped on SQLite
    assert db.migrate(engine) == []
    counts = db.table_counts(engine, ["series_daily", "forecasts", "briefings", "rate_limits"])
    assert counts == {"series_daily": 0, "forecasts": 0, "briefings": 0, "rate_limits": 0}


def test_statement_splitter_respects_dollar_quotes() -> None:
    sql = "SELECT 1;\n-- comment;\nDO $$ BEGIN PERFORM 1; END $$;\nSELECT 2"
    assert db._statements(sql) == ["SELECT 1", "DO $$ BEGIN PERFORM 1; END $$", "SELECT 2"]


def test_upsert_daily_is_idempotent_and_updates(engine: Engine) -> None:
    db.upsert_series_daily(engine, _frame([2.4e8, 2.5e8]))
    db.upsert_series_daily(engine, _frame([2.4e8, 2.5e8]))
    assert db.table_counts(engine, ["series_daily"]) == {"series_daily": 2}
    db.upsert_series_daily(engine, _frame([2.6e8], start="2026-10-02"))  # revision of day 2
    wide = db.read_series(engine)
    assert wide["demand_kwh"].tolist() == [2.4e8, 2.6e8]


def test_read_series_pivots_and_filters(engine: Engine, tmp_path: Path) -> None:
    db.upsert_series_daily(
        engine, pd.concat([_frame([1e8, 2e8]), _frame([0.5, 0.6], "reservoir_pct")])
    )
    wide = db.read_series(engine, ["reservoir_pct"])
    assert list(wide.columns) == ["reservoir_pct"]
    assert isinstance(wide.index, pd.DatetimeIndex)
    empty = db.make_engine(f"sqlite:///{(tmp_path / 'empty.sqlite').as_posix()}")
    db.migrate(empty)
    assert db.read_series(empty).empty


def test_hourly_upsert_and_prune(engine: Engine) -> None:
    old = pd.DataFrame(
        {
            "series": "price_cop_kwh",
            "day": pd.to_datetime(["2026-01-01"]),
            "hour": [1],
            "value": [1.0],
        }
    )
    new = pd.DataFrame(
        {
            "series": "price_cop_kwh",
            "day": pd.to_datetime(["2026-10-20"]),
            "hour": [1],
            "value": [2.0],
        }
    )
    db.upsert_series_hourly(engine, pd.concat([old, new]))
    removed = db.prune_hourly(engine, date(2026, 10, 24), keep_days=90)
    assert removed == 1
    assert db.table_counts(engine, ["series_hourly"]) == {"series_hourly": 1}


def test_hour_constraint_is_enforced(engine: Engine) -> None:
    bad = pd.DataFrame(
        {
            "series": "price_cop_kwh",
            "day": pd.to_datetime(["2026-10-20"]),
            "hour": [25],
            "value": [1.0],
        }
    )
    with pytest.raises(IntegrityError):
        db.upsert_series_hourly(engine, bad)


def test_ingest_log_keeps_last_day_on_error(engine: Engine) -> None:
    db.log_ingest(engine, "xm_daily", date(2026, 10, 20), "ok")
    db.log_ingest(engine, "xm_daily", None, "error", "boom")
    assert db.get_last_day(engine, "xm_daily") == date(2026, 10, 20)
    with engine.connect() as conn:
        status = conn.exec_driver_sql("SELECT status, detail FROM ingest_log").one()
    assert tuple(status) == ("error", "boom")


def test_forecast_quantiles_must_be_ordered(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO model_runs VALUES "
            "('r1', '2026-10-24 00:00:00', '2018-01-01', '2026-10-23', '{}', '{}')"
        )
        with pytest.raises(IntegrityError):
            conn.exec_driver_sql(
                "INSERT INTO forecasts "
                "VALUES ('r1', 'demand', '2026-10-25', 1, 5.0, 4.0, 6.0, NULL)"
            )
