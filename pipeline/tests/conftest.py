from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import Engine

from voltia import db
from voltia.features import calendar_frame

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_json() -> Callable[[str], Any]:
    def _load(name: str) -> Any:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    return _load


@pytest.fixture
def read_text() -> Callable[[str], str]:
    def _read(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return _read


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    eng = db.make_engine(f"sqlite:///{(tmp_path / 'test.sqlite').as_posix()}")
    db.migrate(eng)
    return eng


def make_history(days: int = 760, start: str = "2023-01-01", seed: int = 0) -> pd.DataFrame:
    """Synthetic daily history with every series the features use and a known structure.

    Demand: level with slow growth, weekly cycle, holiday dips and 1 % noise.
    Price: AR(1) on the log scale plus a weekend dip; hydrology and weather are smooth cycles.
    """
    rng = np.random.default_rng(seed)
    index = pd.date_range(start, periods=days, freq="D")
    cal = calendar_frame(index[0], index[-1])
    t = np.arange(days)
    weekly = np.array([1.02, 1.03, 1.03, 1.03, 1.02, 0.94, 0.85])[index.day_of_week]
    holiday = 1 - 0.12 * cal["is_holiday"].to_numpy() * (index.day_of_week < 5)
    demand = 2.2e8 * (1 + 0.00005 * t) * weekly * holiday * np.exp(rng.normal(0, 0.01, days))
    ar = np.zeros(days)
    for i in range(1, days):
        ar[i] = 0.95 * ar[i - 1] + rng.normal(0, 0.08)
    price = np.exp(5.5 + ar - 0.08 * (index.day_of_week >= 5))
    season = np.sin(2 * np.pi * t / 365.25)
    reservoir = 0.6 + 0.15 * season + rng.normal(0, 0.005, days)
    inflows_pct = 1 + 0.3 * season + rng.normal(0, 0.05, days)
    total = demand * 1.01
    thermal = total * (0.3 - 0.1 * season)
    frame = pd.DataFrame(
        {
            "demand_kwh": demand,
            "price_mean_cop_kwh": price,
            "price_max_cop_kwh": price * 1.4,
            "reservoir_pct": reservoir,
            "inflows_pct": inflows_pct,
            "inflows_kwh": inflows_pct * 2.4e8,
            "inflows_hist_mean_kwh": np.full(days, 2.4e8),
            "reservoir_kwh": reservoir * 1.7e10,
            "gen_total_kwh": total,
            "gen_thermal_kwh": thermal,
            "gen_hydro_kwh": total - thermal - total * 0.05,
            "gen_solar_kwh": total * 0.04,
            "gen_wind_kwh": total * 0.01,
            "weather_temp_c": 22 + 1.5 * season + rng.normal(0, 0.5, days),
            "weather_precip_mm": rng.gamma(1.0, 5.0, days),
            # Market state of the price model: dispatch cost follows the settled price with a bias.
            "dispatch_cost": price * 0.85 * np.exp(rng.normal(0, 0.05, days)),
            "contract_price": 250 + 30 * season + rng.normal(0, 2, days),
            "contract_price_unreg": 255 + 30 * season + rng.normal(0, 2, days),
            "scarcity_price": 700 + 40 * season,
            "spill_kwh": np.where(season > 0.4, 3e7 * season, 0.0),
            "turbined_m3": 2e8 * (1 + 0.2 * season) + rng.normal(0, 1e6, days),
            "reservoir_capacity_kwh": np.full(days, 1.7e10),
        },
        index=index,
    )
    oni = pd.Series(np.round(np.sin(t / 200), 2), index=index)
    frame["oni"] = oni.where(index.day == 1)
    frame.index.name = "day"
    return frame


@pytest.fixture
def history() -> pd.DataFrame:
    return make_history()
