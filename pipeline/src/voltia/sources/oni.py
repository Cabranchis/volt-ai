"""Oceanic Niño Index (ONI) from NOAA's Climate Prediction Center.

Each row of the text file is a three-month season with its anomaly. Each value is stored on the
first day of the season's central month, so DJF becomes January.
"""

from __future__ import annotations

import httpx
import pandas as pd
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
_CENTRE_MONTH = {
    "DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
    "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12,
}  # fmt: skip


def parse_oni(text: str) -> pd.DataFrame:
    """Return a frame with columns day (first of the central month) and value (ONI anomaly)."""
    rows: list[tuple[str, float]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[0] not in _CENTRE_MONTH:
            continue
        season, year, _total, anomaly = parts
        rows.append((f"{int(year):04d}-{_CENTRE_MONTH[season]:02d}-01", float(anomaly)))
    frame = pd.DataFrame(rows, columns=["day", "value"])
    frame["day"] = pd.to_datetime(frame["day"])
    return frame


class OniClient:
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
    def fetch(self) -> pd.DataFrame:
        response = self._client.get(ONI_URL)
        response.raise_for_status()
        return parse_oni(response.text)
