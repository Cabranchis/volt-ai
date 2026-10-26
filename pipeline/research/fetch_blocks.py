"""Download the series behind the phase B feature blocks (daily, from 2018) into research/data.

Usage: python fetch_blocks.py [regional] [price_profile] [availability] [restrictions]

Each group is saved to its own CSV so a failed group can be re-run alone. Resource-level metrics
(availability, out-of-merit generation) are summed by plant type with XM's resource catalog.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from voltia.ingest import HYDRO_REGIONS, UNLISTED_RIVER_REGION, XM_RESERVOIR_METRICS, XM_RIVER_METRICS
from voltia.sources.xm import HOURS, XMClient, _to_float, parse_resource_catalog, windows

OUT = Path(__file__).parent / "data"
START = date(2018, 1, 1)


def regional(client: XMClient, end: date) -> None:
    reservoirs = client.hydro_catalog("reservoir")
    rivers = client.hydro_catalog("river")
    unlisted = [(n, r) for n, r in UNLISTED_RIVER_REGION.items() if n not in set(rivers["entity"])]
    rivers = pd.concat([rivers, pd.DataFrame(unlisted, columns=["entity", "region"])])
    catalog = pd.concat(
        [reservoirs.assign(kind="reservoir"), rivers.assign(kind="river")], ignore_index=True
    )
    catalog = catalog[catalog["region"].isin(HYDRO_REGIONS)]
    parts = []
    for kind, entity_id, metrics in (
        ("reservoir", "Embalse", XM_RESERVOIR_METRICS),
        ("river", "Rio", XM_RIVER_METRICS),
    ):
        known = catalog[catalog["kind"] == kind][["entity", "region"]]
        for metric, name in metrics.items():
            frame = client.daily_entities(metric, entity_id, START, end)
            frame = frame.merge(known, on="entity").assign(metric=name)
            parts.append(frame)
            print("regional", name, len(frame), flush=True)
    pd.concat(parts, ignore_index=True)[["metric", "region", "entity", "day", "value"]].to_csv(
        OUT / "blocks_regional.csv", index=False
    )


def price_profile(client: XMClient, end: date) -> None:
    hourly = client.hourly_system("PrecBolsNaci", START, end)
    hourly = hourly[hourly["value"] > 0]
    by_day = hourly.groupby("day")["value"]
    peak = hourly[hourly["hour"].between(18, 21)].groupby("day")["value"].mean()
    night = hourly[hourly["hour"].between(1, 5)].groupby("day")["value"].mean()
    frame = pd.DataFrame(
        {
            "price_peak": peak,
            "price_night": night,
            "price_min": by_day.min(),
            "price_std": by_day.std(),
            "price_hours": by_day.count(),
        }
    )
    frame.to_csv(OUT / "blocks_price_profile.csv", index_label="day")
    print("price_profile", frame.shape, flush=True)


def _by_category(client: XMClient, metric: str, catalog: dict[str, str], end: date) -> pd.DataFrame:
    parts = []
    for s, e in windows(START, end):
        payload = client.fetch("hourly", metric, "Recurso", s, e)
        rows = []
        for item in payload.get("Items", []):
            for entity in item.get("HourlyEntities", []):
                values = entity.get("Values", {})
                hours = [_to_float(values.get(key)) for key in HOURS]
                rows.append((item["Date"], str(values.get("code")), sum(v for v in hours if v is not None)))
        frame = pd.DataFrame(rows, columns=["day", "code", "total"])
        frame["day"] = pd.to_datetime(frame["day"])
        frame["category"] = frame["code"].map(catalog).fillna("other")
        parts.append(frame.groupby(["day", "category"], as_index=False)["total"].sum())
        print(metric, s, flush=True)
    return pd.concat(parts, ignore_index=True)


def availability(client: XMClient, end: date) -> None:
    catalog = client.resource_catalog()
    wide = {}
    for metric, name in (
        ("DispoReal", "dispo_real"),
        ("DispoDeclarada", "dispo_decl"),
        ("DispoCome", "dispo_come"),
        ("GeneFueraMerito", "out_of_merit"),
    ):
        frame = _by_category(client, metric, catalog, end)
        table = frame.pivot_table(index="day", columns="category", values="total", aggfunc="sum")
        for category in table.columns:
            wide[f"{name}_{category}"] = table[category]
    pd.DataFrame(wide).sort_index().to_csv(OUT / "blocks_availability.csv", index_label="day")
    print("availability", len(wide), "columns", flush=True)


def restrictions(client: XMClient, end: date) -> None:
    columns = {}
    for metric, name in (("RestAliv", "restr_relief_cop"), ("RestSinAliv", "restr_plain_cop")):
        hourly = client.hourly_system(metric, START, end)
        columns[name] = hourly.groupby("day")["value"].sum()
        print("restrictions", name, len(hourly), flush=True)
    pd.DataFrame(columns).sort_index().to_csv(OUT / "blocks_restrictions.csv", index_label="day")


GROUPS = {
    "regional": regional,
    "price_profile": price_profile,
    "availability": availability,
    "restrictions": restrictions,
}


def main(names: list[str]) -> None:
    client = XMClient()
    end = date.today() + timedelta(days=1)
    for name in names or list(GROUPS):
        GROUPS[name](client, end)


if __name__ == "__main__":
    main(sys.argv[1:])
