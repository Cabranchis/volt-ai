from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import make_history
from voltia import db
from voltia.cli import app
from voltia.config import get_settings

runner = CliRunner()


@pytest.fixture
def tiny_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "ml.sqlite"
    monkeypatch.setenv("VOLTIA_LOCAL_DB", str(path))
    monkeypatch.setenv("VOLTIA_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    engine = db.make_engine(f"sqlite:///{path.as_posix()}")
    db.migrate(engine)
    wide = make_history(days=500)
    long = wide.reset_index().melt(id_vars="day", var_name="series").dropna()
    db.upsert_series_daily(engine, long)
    return path


def test_train_predict_anomalies_end_to_end(tiny_db: Path) -> None:
    args = ["train", "--predict", "--origins", "2", "--warmup", "1", "--step", "20"]
    result = runner.invoke(app, [*args, "--rounds", "15"])
    assert result.exit_code == 0, result.output
    assert "MASE model=" in result.output
    assert "wrote 44 forecast rows" in result.output

    again = runner.invoke(app, ["predict"])
    assert again.exit_code == 0, again.output

    found = runner.invoke(app, ["anomalies"])
    assert found.exit_code == 0, found.output
    assert "demand_kwh" in found.output

    engine = db.make_engine(f"sqlite:///{tiny_db.as_posix()}")
    counts = db.table_counts(engine, ["model_runs", "forecasts"])
    assert counts == {"model_runs": 1, "forecasts": 44}


def test_predict_without_models_fails_cleanly(tiny_db: Path) -> None:
    result = runner.invoke(app, ["predict"])
    assert result.exit_code == 1
    assert "voltia train" in result.output


def test_train_without_data_fails_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOLTIA_LOCAL_DB", str(tmp_path / "empty.sqlite"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    result = runner.invoke(app, ["train"])
    assert result.exit_code == 1
    assert "backfill" in result.output
