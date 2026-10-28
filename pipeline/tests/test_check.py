from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from voltia import cli, db, ingest
from voltia.cli import app
from voltia.config import Settings, get_settings
from voltia.ingest import Batch, Clients

runner = CliRunner()


def _daily(series: str, days: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"series": series, "day": pd.to_datetime(days), "value": [1.0] * len(days)})


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


def _patch_fetchers(
    monkeypatch: pytest.MonkeyPatch, price_days: list[str], demand_days: list[str]
) -> None:
    monkeypatch.setattr(
        ingest, "fetch_xm_price", lambda *_a: Batch(daily=_daily("price_mean_cop_kwh", price_days))
    )
    monkeypatch.setattr(
        ingest, "fetch_xm_daily", lambda *_a: Batch(daily=_daily("demand_kwh", demand_days))
    )


def test_newest_complete_day_is_the_earlier_of_price_and_demand(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    _patch_fetchers(monkeypatch, ["2026-10-24", "2026-10-25"], ["2026-10-23", "2026-10-24"])
    clients = Clients(None, None, None)  # type: ignore[arg-type]
    assert ingest.newest_complete_day(clients, settings, date(2026, 10, 28)) == date(2026, 10, 24)


def test_newest_complete_day_is_none_when_a_series_has_no_complete_day(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    _patch_fetchers(monkeypatch, ["2026-10-24"], [])
    clients = Clients(None, None, None)  # type: ignore[arg-type]
    assert ingest.newest_complete_day(clients, settings, date(2026, 10, 28)) is None


@pytest.fixture
def local_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "check.sqlite"
    monkeypatch.setenv("VOLTIA_LOCAL_DB", str(path))
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    db.migrate(db.make_engine(get_settings().resolved_database_url))
    return path


def _run_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ready: date | Exception | None
) -> tuple[str, str]:
    def fake(*_a: object) -> date | None:
        if isinstance(ready, Exception):
            raise ready
        return ready

    monkeypatch.setattr(cli, "newest_complete_day", fake)
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 0, result.output  # never a red run
    return result.output, output.read_text(encoding="utf-8")


def _store_run(data_end: str) -> None:
    engine = db.make_engine(get_settings().resolved_database_url)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO model_runs (run_id, trained_at, data_start, data_end, params, metrics) "
            "VALUES ('r1', '2026-10-28 01:00:00', '2018-01-01', "
            f"'{data_end}', '{{}}', '{{}}')"
        )


def test_check_says_true_when_xm_is_ahead_of_the_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, local_db: Path
) -> None:
    _store_run("2026-10-24")
    out, written = _run_check(monkeypatch, tmp_path, date(2026, 10, 25))
    assert "new_data=true" in out
    assert written.strip() == "new_data=true"


def test_check_says_false_when_the_model_already_has_that_day(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, local_db: Path
) -> None:
    _store_run("2026-10-25")
    out, written = _run_check(monkeypatch, tmp_path, date(2026, 10, 25))
    assert "new_data=false" in out
    assert written.strip() == "new_data=false"


def test_check_says_true_before_the_first_model_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, local_db: Path
) -> None:
    _, written = _run_check(monkeypatch, tmp_path, date(2026, 10, 25))
    assert written.strip() == "new_data=true"


def test_check_says_false_and_warns_when_xm_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, local_db: Path
) -> None:
    _store_run("2026-10-24")
    out, written = _run_check(monkeypatch, tmp_path, RuntimeError("XM is down"))
    assert "::warning::" in out
    assert written.strip() == "new_data=false"


def test_check_says_false_when_xm_has_no_complete_day(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, local_db: Path
) -> None:
    _store_run("2026-10-24")
    _, written = _run_check(monkeypatch, tmp_path, None)
    assert written.strip() == "new_data=false"


def test_the_model_data_end_is_taken_from_the_newest_run(local_db: Path) -> None:
    engine = db.make_engine(get_settings().resolved_database_url)
    with engine.begin() as conn:
        for run_id, trained_at, data_end in (
            ("old", "2026-10-26 01:00:00", "2026-10-22"),
            ("new", "2026-10-28 01:00:00", "2026-10-25"),
            ("mid", "2026-10-27 01:00:00", "2026-10-24"),
        ):
            conn.exec_driver_sql(
                "INSERT INTO model_runs "
                "(run_id, trained_at, data_start, data_end, params, metrics) "
                f"VALUES ('{run_id}', '{trained_at}', '2018-01-01', '{data_end}', '{{}}', '{{}}')"
            )
    assert db.latest_model_data_end(engine) == date(2026, 10, 25)


def test_check_survives_a_failure_before_it_even_starts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, local_db: Path
) -> None:
    def broken() -> Settings:
        raise ValueError("bad environment")

    monkeypatch.setattr(cli, "get_settings", broken)
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 0
    assert "::warning::" in result.output
    assert output.read_text(encoding="utf-8").strip() == "new_data=false"
