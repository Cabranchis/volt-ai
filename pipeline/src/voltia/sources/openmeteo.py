"""Daily weather for the main demand centres of Colombia from Open-Meteo (no API key).

The archive API lags a few days behind, so recent days come from the forecast API
(`past_days`), which serves observed-based analysis for the past.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import httpx
import pandas as pd
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_LAG_DAYS = 7
MAX_PAST_DAYS = 92
DAILY_VARS = "temperature_2m_mean,precipitation_sum"

# Bogotá, Medellín, Cali, Barranquilla: the largest load centres.
CITIES: dict[str, tuple[float, float]] = {
    "bogota": (4.71, -74.07),
    "medellin": (6.25, -75.57),
    "cali": (3.45, -76.53),
    "barranquilla": (10.96, -74.80),
}


# Near the main reservoirs (Guatapé and San Carlos in Antioquia, Chivor in Boyacá, Betania in Huila,
# Salvajina in Cauca). The grid of the model is coarser than the error of these coordinates.
BASINS: dict[str, tuple[float, float]] = {
    "guatape": (6.28, -75.17),
    "san_carlos": (6.18, -74.85),
    "chivor": (4.88, -73.37),
    "betania": (2.70, -75.43),
    "salvajina": (3.05, -76.70),
}
FORECAST_POINTS: dict[str, tuple[float, float]] = {**CITIES, **BASINS}
FORECAST_DAYS = 16  # the most the API serves
# Pinned, not left to "best_match": Open-Meteo may change the model behind that choice, which would
# mix regimes in a log meant to be read months later. GFS serves all 16 days without gaps (ECMWF's
# last day comes back empty).
FORECAST_MODEL = "gfs_seamless"
FORECAST_COLUMNS = ["issued", "location", "day", "lead_days", "precip_mm", "temp_c", "model"]


def parse_forecast(
    payload: dict[str, Any] | list[dict[str, Any]], names: list[str], issued: date
) -> pd.DataFrame:
    """One row per location and forecast day, with how many days ahead it was issued.

    Every location must come back with all `FORECAST_DAYS` days, from the issue date, and without
    gaps: a forecast that is incomplete is refused rather than stored short, because it could be
    completed later by a newer model run and still carry the same issue date.
    """
    locations = payload if isinstance(payload, list) else [payload]
    if len(locations) != len(names):
        raise ValueError(f"expected {len(names)} locations, got {len(locations)}")
    frames = []
    for name, location in zip(names, locations, strict=True):
        daily = location.get("daily", {})
        frames.append(
            pd.DataFrame(
                {
                    "location": name,
                    "day": pd.to_datetime(daily.get("time", [])),
                    "precip_mm": pd.to_numeric(daily.get("precipitation_sum", []), errors="coerce"),
                    "temp_c": pd.to_numeric(daily.get("temperature_2m_mean", []), errors="coerce"),
                }
            )
        )
    stacked = pd.concat(frames, ignore_index=True)
    stacked["issued"] = pd.Timestamp(issued)
    stacked["lead_days"] = (stacked["day"] - stacked["issued"]).dt.days
    wanted = list(range(FORECAST_DAYS))
    for place, part in stacked.groupby("location"):
        if sorted(part["lead_days"]) != wanted:
            raise ValueError(
                f"{place}: the forecast does not cover the {FORECAST_DAYS} days from {issued}"
            )
    if stacked[["precip_mm", "temp_c"]].isna().any().any():
        raise ValueError("the forecast has missing values")
    stacked["model"] = FORECAST_MODEL
    return stacked[FORECAST_COLUMNS].reset_index(drop=True)


def parse_weather(payload: dict[str, Any] | list[dict[str, Any]]) -> pd.DataFrame:
    """Average the cities into one frame with columns day, temp_c and precip_mm."""
    locations = payload if isinstance(payload, list) else [payload]
    frames = []
    for location in locations:
        daily = location.get("daily", {})
        frames.append(
            pd.DataFrame(
                {
                    "day": pd.to_datetime(daily.get("time", [])),
                    "temp_c": pd.to_numeric(daily.get("temperature_2m_mean", []), errors="coerce"),
                    "precip_mm": pd.to_numeric(daily.get("precipitation_sum", []), errors="coerce"),
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=["day", "temp_c", "precip_mm"])
    stacked = pd.concat(frames, ignore_index=True)
    return (
        stacked.groupby("day", as_index=False)[["temp_c", "precip_mm"]]
        .mean()
        .dropna(subset=["temp_c", "precip_mm"])
    )


class OpenMeteoClient:
    def __init__(self, timeout_s: float = 60.0, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        self._client.close()

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        reraise=True,
    )
    def _get(self, url: str, params: dict[str, Any]) -> Any:
        response = self._client.get(url, params=params)
        if response.status_code == 429 or response.status_code >= 500:
            raise httpx.TransportError(f"Open-Meteo HTTP {response.status_code}")
        response.raise_for_status()
        return response.json()

    def _coords(self) -> dict[str, str]:
        return {
            "latitude": ",".join(str(lat) for lat, _ in CITIES.values()),
            "longitude": ",".join(str(lon) for _, lon in CITIES.values()),
        }

    def forecast(self, today: date) -> pd.DataFrame:
        """The forecast issued now for today and the next days, at every forecast point."""
        names = list(FORECAST_POINTS)
        params: dict[str, Any] = {
            "latitude": ",".join(str(FORECAST_POINTS[n][0]) for n in names),
            "longitude": ",".join(str(FORECAST_POINTS[n][1]) for n in names),
            "forecast_days": FORECAST_DAYS,
            "models": FORECAST_MODEL,
            "daily": DAILY_VARS,
            "timezone": "America/Bogota",
        }
        return parse_forecast(self._get(FORECAST_URL, params), names, today)

    def weather(self, start: date, end: date, today: date) -> pd.DataFrame:
        """Daily weather from start to end, using the archive for old days and past_days for new."""
        parts: list[pd.DataFrame] = []
        archive_end = min(end, today - timedelta(days=ARCHIVE_LAG_DAYS))
        cursor = start
        while cursor <= archive_end:
            stop = min(date(cursor.year, 12, 31), archive_end)
            params: dict[str, Any] = {
                **self._coords(),
                "start_date": cursor.isoformat(),
                "end_date": stop.isoformat(),
                "daily": DAILY_VARS,
                "timezone": "America/Bogota",
            }
            parts.append(parse_weather(self._get(ARCHIVE_URL, params)))
            cursor = stop + timedelta(days=1)
        if end > archive_end:
            recent_start = max(start, archive_end + timedelta(days=1))
            past_days = min((today - recent_start).days, MAX_PAST_DAYS)
            params = {
                **self._coords(),
                "past_days": max(past_days, 0),
                "forecast_days": 1,
                "daily": DAILY_VARS,
                "timezone": "America/Bogota",
            }
            recent = parse_weather(self._get(FORECAST_URL, params))
            parts.append(
                recent[
                    (recent["day"] >= pd.Timestamp(recent_start))
                    & (recent["day"] <= pd.Timestamp(end))
                ]
            )
        parts = [p for p in parts if not p.empty]
        if not parts:
            return pd.DataFrame(columns=["day", "temp_c", "precip_mm"])
        return pd.concat(parts, ignore_index=True).drop_duplicates("day", keep="last")
