"""Daily briefing: a short executive summary in Spanish and English, stored once per day.

The facts come from the database and the text is built from them with a fixed template, so the
briefing exists even without a language model. When a Gemini key is set, the model only rewrites
the template into smoother prose and is rejected if it introduces a number that is not in the
facts; any failure keeps the template.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
import structlog
from google import genai
from google.genai import types

log = structlog.get_logger()

Lang = Literal["es", "en"]
LANGS: tuple[Lang, ...] = ("es", "en")
MIX = [f"gen_{c}_kwh" for c in ("hydro", "thermal", "solar", "wind", "cogen", "other")]
GWH = 1_000_000.0


@dataclass(frozen=True)
class Facts:
    """The figures a briefing may quote. Any field can be None when its series is empty."""

    day: date
    demand_gwh: float | None
    demand_week_pct: float | None
    price_cop_kwh: float | None
    price_week_pct: float | None
    reservoir_pct: float | None
    reservoir_week_points: float | None
    oni: float | None
    thermal_share_pct: float | None
    next_week_demand_gwh: float | None


def _last(series: pd.Series) -> tuple[date, float] | None:
    clean = series.dropna()
    return (clean.index[-1].date(), float(clean.iloc[-1])) if len(clean) else None


def _week_ago(series: pd.Series, day: date) -> float | None:
    value = series.get(pd.Timestamp(day) - pd.Timedelta(days=7))
    return None if value is None or pd.isna(value) else float(value)


def _pct(now: float, before: float | None) -> float | None:
    return None if before is None or before == 0 else (now - before) / before * 100


def build_facts(history: pd.DataFrame, next_week_demand_kwh: float | None) -> Facts | None:
    """Collect the figures for the latest settled demand day. None if there is no demand."""
    if "demand_kwh" not in history.columns:
        return None
    latest = _last(history["demand_kwh"])
    if latest is None:
        return None
    day, demand = latest

    price = reservoir = oni = thermal = None
    price_pct = reservoir_pts = None
    if "price_mean_cop_kwh" in history.columns and (p := _last(history["price_mean_cop_kwh"])):
        price = p[1]
        price_pct = _pct(price, _week_ago(history["price_mean_cop_kwh"], p[0]))
    if "reservoir_pct" in history.columns and (r := _last(history["reservoir_pct"])):
        reservoir = r[1] * 100  # stored as a fraction
        before = _week_ago(history["reservoir_pct"], r[0])
        reservoir_pts = None if before is None else reservoir - before * 100
    if "oni" in history.columns and (o := _last(history["oni"])):
        oni = o[1]
    if all(c in history.columns for c in MIX):
        row = history.loc[pd.Timestamp(day), MIX].to_numpy(dtype=float)
        if not np.isnan(row).any() and row.sum() > 0:
            thermal = float(row[MIX.index("gen_thermal_kwh")] / row.sum() * 100)

    return Facts(
        day=day,
        demand_gwh=demand / GWH,
        demand_week_pct=_pct(demand, _week_ago(history["demand_kwh"], day)),
        price_cop_kwh=price,
        price_week_pct=price_pct,
        reservoir_pct=reservoir,
        reservoir_week_points=reservoir_pts,
        oni=oni,
        thermal_share_pct=thermal,
        next_week_demand_gwh=None if next_week_demand_kwh is None else next_week_demand_kwh / GWH,
    )


def _num(value: float, lang: Lang, digits: int = 1) -> str:
    text = f"{value:.{digits}f}"
    return text.replace(".", ",") if lang == "es" else text


def _signed(value: float, lang: Lang, digits: int = 1) -> str:
    return ("+" if value >= 0 else "\N{MINUS SIGN}") + _num(abs(value), lang, digits)


def _oni_phase(value: float, lang: Lang) -> str:
    phases = {
        "es": ("El Niño", "La Niña", "condiciones neutras"),
        "en": ("El Niño", "La Niña", "neutral conditions"),
    }[lang]
    return phases[0] if value >= 0.5 else phases[1] if value <= -0.5 else phases[2]


def template(facts: Facts, lang: Lang) -> str:
    """Build the briefing from the facts. Every sentence is skipped when its figures are missing."""
    es = lang == "es"
    out: list[str] = []
    if facts.demand_gwh is not None:
        week = (
            ""
            if facts.demand_week_pct is None
            else f", {_signed(facts.demand_week_pct, lang)} % frente a la semana anterior"
            if es
            else f", {_signed(facts.demand_week_pct, lang)} % against the previous week"
        )
        out.append(
            f"La demanda del {facts.day.isoformat()} fue de "
            f"{_num(facts.demand_gwh, lang)} GWh{week}."
            if es
            else f"Demand on {facts.day.isoformat()} was {_num(facts.demand_gwh, lang)} GWh{week}."
        )
    if facts.price_cop_kwh is not None:
        week = (
            ""
            if facts.price_week_pct is None
            else f" ({_signed(facts.price_week_pct, lang, 0)} % en una semana)"
            if es
            else f" ({_signed(facts.price_week_pct, lang, 0)} % in a week)"
        )
        value = _num(facts.price_cop_kwh, lang, 0)
        out.append(
            f"El precio de bolsa promedió {value} COP/kWh{week}."
            if es
            else f"The spot price averaged {value} COP/kWh{week}."
        )
    if facts.reservoir_pct is not None:
        pts = (
            ""
            if facts.reservoir_week_points is None
            else f" ({_signed(facts.reservoir_week_points, lang)} puntos en la semana)"
            if es
            else f" ({_signed(facts.reservoir_week_points, lang)} points over the week)"
        )
        level = _num(facts.reservoir_pct, lang)
        out.append(
            f"Los embalses están al {level} %{pts}."
            if es
            else f"Reservoirs stand at {level} %{pts}."
        )
    if facts.oni is not None:
        phase = _oni_phase(facts.oni, lang)
        out.append(
            f"El índice ONI es {_num(facts.oni, lang, 2)}, señal de {phase}."
            if es
            else f"The ONI index is {_num(facts.oni, lang, 2)}, a sign of {phase}."
        )
    if facts.thermal_share_pct is not None:
        share = _num(facts.thermal_share_pct, lang, 0)
        out.append(
            f"Las térmicas aportaron el {share} % de la generación."
            if es
            else f"Thermal plants supplied {share} % of generation."
        )
    if facts.next_week_demand_gwh is not None:
        gwh = _num(facts.next_week_demand_gwh, lang)
        out.append(
            f"El modelo espera unos {gwh} GWh de demanda dentro de una semana."
            if es
            else f"The model expects about {gwh} GWh of demand a week from now."
        )
    return " ".join(out)


_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def numbers_in(text: str) -> set[str]:
    """Numbers as written in `text`, with the decimal comma normalised to a point."""
    return {m.replace(",", ".") for m in _NUMBER.findall(text)}


def is_faithful(candidate: str, reference: str) -> bool:
    """True when `candidate` quotes no number that `reference` does not already contain."""
    return bool(candidate.strip()) and numbers_in(candidate) <= numbers_in(reference)


def polish(text: str, lang: Lang, api_key: str, model: str) -> str | None:
    """Ask Gemini to rewrite `text` as fluid prose. None on any failure or unfaithful output."""
    try:
        language = "Spanish" if lang == "es" else "English"
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=(
                f"Rewrite this Colombian electricity-market briefing in {language} as one short, "
                "neutral paragraph for energy analysts. Use only the facts and numbers given; "
                "do not add, round or compute any figure, and do not give advice.\n\n" + text
            ),
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=400),
        )
        candidate = (response.text or "").strip()
    except Exception as exc:  # the briefing must survive any provider failure
        log.warning("briefing_polish_failed", error=type(exc).__name__)
        return None
    if not is_faithful(candidate, text):
        log.warning("briefing_polish_rejected", reason="introduced a number")
        return None
    return candidate
