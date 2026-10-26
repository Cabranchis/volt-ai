from __future__ import annotations

from pathlib import Path

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
