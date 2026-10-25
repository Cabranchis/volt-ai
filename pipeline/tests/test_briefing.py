from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from voltia import briefing, db
from voltia.briefing import build_facts, is_faithful, numbers_in, polish, template
from voltia.cli import app
from voltia.config import get_settings

DAYS = pd.date_range("2026-10-01", "2026-10-21")


def history() -> pd.DataFrame:
    frame = pd.DataFrame(index=DAYS)
    frame["demand_kwh"] = np.linspace(240e6, 245.3e6, len(DAYS))
    frame["price_mean_cop_kwh"] = 300.0
    frame.loc[DAYS[-1], "price_mean_cop_kwh"] = 330.0
    frame["reservoir_pct"] = 0.6
    frame["oni"] = 2.16
    shares = {"hydro": 60, "thermal": 30, "solar": 4, "wind": 1, "cogen": 3, "other": 2}
    for name, share in shares.items():
        frame[f"gen_{name}_kwh"] = share * 1e6
    return frame


def test_facts_use_the_latest_demand_day_and_compare_with_a_week_earlier() -> None:
    facts = build_facts(history(), next_week_demand_kwh=250e6)
    assert facts is not None
    assert facts.day == date(2026, 10, 21)
    assert facts.demand_gwh == pytest.approx(245.3)
    assert facts.price_week_pct == pytest.approx(10.0)
    assert facts.thermal_share_pct == pytest.approx(30.0)
    assert facts.next_week_demand_gwh == pytest.approx(250.0)


def test_no_demand_means_no_facts() -> None:
    assert build_facts(pd.DataFrame(), None) is None
    assert build_facts(history().drop(columns="demand_kwh"), None) is None


def test_template_is_bilingual_and_quotes_only_the_facts() -> None:
    facts = build_facts(history(), 250e6)
    assert facts is not None
    es, en = template(facts, "es"), template(facts, "en")
    assert "245,3 GWh" in es
    assert "245.3 GWh" in en
    assert "El Niño" in es
    assert "El Niño" in en
    assert "+10 %" in en


def test_template_skips_sentences_whose_figures_are_missing() -> None:
    facts = build_facts(history()[["demand_kwh"]], None)
    assert facts is not None
    text = template(facts, "en")
    assert text.startswith("Demand on 2026-10-21")
    assert "price" not in text
    assert "Reservoirs" not in text


def test_a_rewrite_that_invents_a_number_is_rejected() -> None:
    reference = "Demand was 245.3 GWh, 2.2 % above last week."
    assert is_faithful("Demand reached 245.3 GWh, up 2.2 % in a week.", reference)
    assert not is_faithful("Demand reached 250 GWh.", reference)
    assert not is_faithful("   ", reference)
    assert numbers_in("245,3 y 2.20") == {"245.3", "2.20"}


def test_brief_command_stores_both_languages_from_the_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VOLTIA_LOCAL_DB", str(tmp_path / "brief.sqlite"))
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("GOOGLE_GENERATIVE_AI_API_KEY", "")
    get_settings.cache_clear()
    engine = db.make_engine(get_settings().resolved_database_url)
    db.migrate(engine)
    long = history()[["demand_kwh"]].reset_index(names="day").assign(series="demand_kwh")
    frame = long.rename(columns={"demand_kwh": "value"})[["series", "day", "value"]]
    db.upsert_series_daily(engine, frame)

    runner = CliRunner()
    for _ in range(2):  # rerunning must replace, not duplicate
        result = runner.invoke(app, ["brief"])
        assert result.exit_code == 0, result.output
    with engine.connect() as conn:
        rows = conn.exec_driver_sql("SELECT lang, source FROM briefings ORDER BY lang").all()
    assert [tuple(r) for r in rows] == [("en", "template"), ("es", "template")]


def test_brief_command_fails_cleanly_without_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VOLTIA_LOCAL_DB", str(tmp_path / "empty.sqlite"))
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    result = CliRunner().invoke(app, ["brief"])
    assert result.exit_code == 1
    assert "no demand data" in result.output


def _fake_genai(monkeypatch: pytest.MonkeyPatch, reply: str | Exception) -> None:
    class Models:
        def generate_content(self, **_: object) -> object:
            if isinstance(reply, Exception):
                raise reply
            return SimpleNamespace(text=reply)

    class Client:
        def __init__(self, **_: object) -> None:
            self.models = Models()

    monkeypatch.setattr(briefing.genai, "Client", Client)


def test_polish_accepts_a_faithful_rewrite(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_genai(monkeypatch, "Demand hit 245.3 GWh.")
    assert polish("Demand was 245.3 GWh.", "en", "key", "m") == "Demand hit 245.3 GWh."


def test_polish_falls_back_on_invented_numbers_and_on_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_genai(monkeypatch, "Demand hit 999 GWh.")
    assert polish("Demand was 245.3 GWh.", "en", "key", "m") is None
    _fake_genai(monkeypatch, RuntimeError("503 overloaded"))
    assert polish("Demand was 245.3 GWh.", "en", "key", "m") is None


def test_template_formats_drops_and_percent_levels() -> None:
    frame = history()
    frame.loc[DAYS[-1], "price_mean_cop_kwh"] = 270.0  # 10 % under the 300 of a week earlier
    frame.loc[DAYS[-8], "reservoir_pct"] = 0.58
    facts = build_facts(frame, None)
    assert facts is not None
    text = template(facts, "en")
    assert "\N{MINUS SIGN}10 % in a week" in text
    assert "Reservoirs stand at 60.0 % (+2.0 points over the week)" in text
