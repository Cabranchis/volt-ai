from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
import typer
from typer.testing import CliRunner

from voltia.cli import _report, app, today_bogota
from voltia.config import Settings, get_settings
from voltia.ingest import Result

runner = CliRunner()


@pytest.fixture(autouse=True)
def local_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "cli.sqlite"
    monkeypatch.setenv("VOLTIA_LOCAL_DB", str(path))
    monkeypatch.setenv("DATABASE_URL", "")  # an empty env var beats pipeline/.env
    get_settings.cache_clear()
    return path


def test_migrate_then_status() -> None:
    first = runner.invoke(app, ["migrate"])
    assert first.exit_code == 0
    assert "0001_init" in first.output
    again = runner.invoke(app, ["migrate"])
    assert "nothing to do" in again.output
    status = runner.invoke(app, ["status"])
    assert status.exit_code == 0
    assert "series_daily" in status.output


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    for command in ("migrate", "backfill", "update", "status"):
        assert command in result.output


def test_today_is_a_date() -> None:
    assert today_bogota().year >= 2026


def test_postgres_urls_are_normalised_for_psycopg() -> None:
    for raw in ("postgres://u:p@h/db", "postgresql://u:p@h/db"):
        url = Settings(database_url=raw, _env_file=None).resolved_database_url  # type: ignore[call-arg]
        assert url == "postgresql+psycopg://u:p@h/db"


def test_sqlite_is_the_default(local_db: Path) -> None:
    url = Settings(_env_file=None).resolved_database_url  # type: ignore[call-arg]
    assert url.startswith("sqlite:///")
    assert local_db.parent.exists()


def test_a_failing_market_dataset_does_not_fail_the_run() -> None:
    core = Result("xm_price", True, 5, None, "ok")
    market = Result("xm_market", False, 0, None, "XMTransientError: down")
    _report([core, market])  # the price model copes with missing market series
    with pytest.raises(typer.Exit):
        _report([Result("xm_price", False, 0, None, "boom"), market])


def test_archive_writes_each_table_and_a_manifest(tmp_path: Path, local_db: Path) -> None:
    out = tmp_path / "backup"
    runner.invoke(app, ["migrate"])
    with sqlite3.connect(local_db) as conn:
        conn.execute(
            "INSERT INTO forecast_log VALUES "
            "('demand_kwh', '2026-10-01', '2026-10-02', 1, 'r1', '2026-10-01 12:00:00', 1, 2, 3)"
        )
        conn.execute(
            "INSERT INTO model_runs (run_id, trained_at, data_start, data_end, params, metrics) "
            "VALUES ('r1', '2026-10-01 12:00:00', '2018-01-01', '2026-09-30', "
            "'{\"a\": 1}', '{\"mase\": 1.2}')"
        )
    result = runner.invoke(app, ["archive", "--out", str(out), "--allow-sqlite"])
    assert result.exit_code == 0, result.output
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["tables"]) == {"forecast_log", "weather_forecast_log", "model_runs"}
    assert manifest["tables"]["forecast_log"]["rows"] == 1
    assert manifest["tables"]["model_runs"]["rows"] == 1
    for table, info in manifest["tables"].items():
        assert info["sha256"] == hashlib.sha256((out / f"{table}.csv.gz").read_bytes()).hexdigest()
        with gzip.open(out / f"{table}.csv.gz", "rt", encoding="utf-8") as handle:
            assert handle.readline().strip()  # the header survives even when the table is empty
    with gzip.open(out / "forecast_log.csv.gz", "rt", encoding="utf-8") as handle:
        assert "demand_kwh" in handle.read()
    runs = pd.read_csv(out / "model_runs.csv.gz")
    assert json.loads(runs.loc[0, "metrics"]) == {"mase": 1.2}  # JSON text, not a Python repr


def test_archive_refuses_a_database_that_is_not_postgresql(tmp_path: Path) -> None:
    result = runner.invoke(app, ["archive", "--out", str(tmp_path / "backup")])
    assert result.exit_code == 1
    assert not (tmp_path / "backup" / "manifest.json").exists()
