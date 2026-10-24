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
