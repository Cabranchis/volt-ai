"""Client and parsers for the public XM API (Colombian power market operator).

Endpoint: POST {base}/{hourly|daily|lists} with a JSON body. One request covers at most 31 days.
Parsers are pure functions over the decoded JSON so tests can run on recorded responses.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import httpx
import pandas as pd
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = structlog.get_logger()

MAX_WINDOW_DAYS = 31
HOURS = [f"Hour{h:02d}" for h in range(1, 25)]

# Resource type (XM "Type") to the category stored in series_daily.
TYPE_CATEGORY = {
    "HIDRAULICA": "hydro",
    "TERMICA": "thermal",
    "SOLAR": "solar",
    "EOLICA": "wind",
    "COGENERADOR": "cogen",
}
OTHER_CATEGORY = "other"


class XMError(RuntimeError):
    """The XM API answered with something that is not data (unknown metric, bad request)."""


class XMTransientError(XMError):
    """A server-side or network problem worth retrying."""


def windows(start: date, end: date, size: int = MAX_WINDOW_DAYS) -> Iterator[tuple[date, date]]:
    """Split [start, end] into consecutive inclusive windows of at most size days."""
    if end < start:
        return
    cursor = start
    while cursor <= end:
        stop = min(cursor + timedelta(days=size - 1), end)
        yield cursor, stop
        cursor = stop + timedelta(days=1)


def _to_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def parse_daily(payload: dict[str, Any], entity_id: str = "Sistema") -> pd.DataFrame:
    """Daily metric payload to a frame with columns day and value."""
    rows: list[tuple[str, float]] = []
    for item in payload.get("Items", []):
        for entity in item.get("DailyEntities", []):
            value = _to_float(entity.get("Value"))
            if entity.get("Id") == entity_id and value is not None:
                rows.append((item["Date"], value))
    frame = pd.DataFrame(rows, columns=["day", "value"])
    frame["day"] = pd.to_datetime(frame["day"])
    return frame


def parse_hourly(payload: dict[str, Any], entity_id: str = "Sistema") -> pd.DataFrame:
    """Hourly metric payload to a frame with columns day, hour (1..24) and value."""
    rows: list[tuple[str, int, float]] = []
    for item in payload.get("Items", []):
        for entity in item.get("HourlyEntities", []):
            if entity.get("Id") != entity_id:
                continue
            values = entity.get("Values", {})
            for hour, key in enumerate(HOURS, start=1):
                value = _to_float(values.get(key))
                if value is not None:
                    rows.append((item["Date"], hour, value))
    frame = pd.DataFrame(rows, columns=["day", "hour", "value"])
    frame["day"] = pd.to_datetime(frame["day"])
    return frame


def parse_generation_by_resource(payload: dict[str, Any]) -> pd.DataFrame:
    """Hourly generation by resource payload to daily kWh per resource code."""
    rows: list[tuple[str, str, float]] = []
    for item in payload.get("Items", []):
        for entity in item.get("HourlyEntities", []):
            values = entity.get("Values", {})
            hourly = [_to_float(values.get(key)) for key in HOURS]
            total = sum(v for v in hourly if v is not None)
            rows.append((item["Date"], str(values.get("code")), total))
    frame = pd.DataFrame(rows, columns=["day", "code", "kwh"])
    frame["day"] = pd.to_datetime(frame["day"])
    return frame.groupby(["day", "code"], as_index=False)[["kwh"]].sum()


def parse_resource_catalog(payload: dict[str, Any]) -> dict[str, str]:
    """ListadoRecursos payload to a map of resource code to category (hydro, thermal, ...)."""
    catalog: dict[str, str] = {}
    for item in payload.get("Items", []):
        for entity in item.get("ListEntities", []):
            values = entity.get("Values", {})
            code = values.get("Code")
            if code:
                kind = str(values.get("Type", "")).upper()
                catalog[str(code)] = TYPE_CATEGORY.get(kind, OTHER_CATEGORY)
    return catalog


def mix_by_category(by_resource: pd.DataFrame, catalog: dict[str, str]) -> pd.DataFrame:
    """Sum daily resource generation into categories. Unknown codes count as 'other'."""
    categorised = by_resource.assign(
        category=by_resource["code"].map(catalog).fillna(OTHER_CATEGORY)
    )
    return categorised.groupby(["day", "category"], as_index=False)[["kwh"]].sum()


class XMClient:
    """Thin HTTP client with retries. Pass an httpx.Client to inject a transport in tests."""

    def __init__(
        self,
        base_url: str = "https://servapibi.xm.com.co",
        timeout_s: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        self._client.close()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, XMTransientError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        reraise=True,
    )
    def _post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(f"{self._base}/{endpoint}", json=body)
        if response.status_code >= 500 or response.status_code == 429:
            raise XMTransientError(f"{endpoint}: HTTP {response.status_code}")
        if response.status_code >= 400:
            raise XMError(f"{endpoint}: HTTP {response.status_code}: {response.text[:200]}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise XMError(f"{body.get('MetricId')}: {response.text[:200]}") from exc
        if not isinstance(payload, dict):
            raise XMError(f"{body.get('MetricId')}: unexpected payload type")
        return payload

    def fetch(
        self, endpoint: str, metric: str, entity: str, start: date, end: date
    ) -> dict[str, Any]:
        """One request for a window of at most 31 days."""
        if (end - start).days + 1 > MAX_WINDOW_DAYS:
            raise ValueError(f"window longer than {MAX_WINDOW_DAYS} days")
        body = {
            "MetricId": metric,
            "StartDate": start.isoformat(),
            "EndDate": end.isoformat(),
            "Entity": entity,
            "Filter": [],
        }
        return self._post(endpoint, body)

    def daily_system(self, metric: str, start: date, end: date) -> pd.DataFrame:
        parts = [
            parse_daily(self.fetch("daily", metric, "Sistema", s, e))
            for s, e in windows(start, end)
        ]
        return _concat(parts, ["day", "value"])

    def hourly_system(self, metric: str, start: date, end: date) -> pd.DataFrame:
        parts = [
            parse_hourly(self.fetch("hourly", metric, "Sistema", s, e))
            for s, e in windows(start, end)
        ]
        return _concat(parts, ["day", "hour", "value"])

    def generation_mix(self, start: date, end: date, catalog: dict[str, str]) -> pd.DataFrame:
        """Daily generation in kWh per category, aggregated window by window to bound memory."""
        parts = []
        for s, e in windows(start, end):
            payload = self.fetch("hourly", "Gene", "Recurso", s, e)
            parts.append(mix_by_category(parse_generation_by_resource(payload), catalog))
            log.info("xm.mix.window", start=s.isoformat(), end=e.isoformat())
        return _concat(parts, ["day", "category", "kwh"])

    def resource_catalog(self) -> dict[str, str]:
        payload = self._post("lists", {"MetricId": "ListadoRecursos", "Entity": "Sistema"})
        return parse_resource_catalog(payload)


def _concat(parts: list[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
    parts = [p for p in parts if not p.empty]
    if not parts:
        return pd.DataFrame(columns=columns)
    return pd.concat(parts, ignore_index=True).drop_duplicates(
        subset=[c for c in columns if c not in ("value", "kwh")], keep="last"
    )
