"""Download the exchange rate and the oil price the fx and oil feature blocks use.

Both are public and need no key:
  - TRM, the representative exchange rate of the peso (Superfinanciera, open data portal dataset
    32sa-8pi3, CC BY-SA 4.0). Each row is valid from `vigenciadesde` to `vigenciahasta`; a rate is
    announced the business day before it applies, and a Friday rate holds for the weekend.
  - Brent, the daily spot price (FRED series DCOILBRENTEU, from the US Energy Information
    Administration). Business days only; FRED publishes it about five days late.

Each is spread over the calendar days (weekends and holidays repeat the last value) and saved with
the other blocks, so the experiments can model how late each one arrives (PUBLICATION_LAG in
harness.py) instead of assuming it is known at once.

    uv run python research/fetch_fx_oil.py

Writes research/data/blocks_fx_oil.csv (day, trm, brent).
"""

from __future__ import annotations

import io
from pathlib import Path

import httpx
import pandas as pd

OUT = Path(__file__).parent / "data" / "blocks_fx_oil.csv"
START = pd.Timestamp("2018-01-01")
TRM_URL = "https://www.datos.gov.co/resource/32sa-8pi3.json"
BRENT_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU"


def fetch_trm(client: httpx.Client) -> pd.Series:
    rows = client.get(
        TRM_URL, params={"$limit": 50000, "$order": "vigenciadesde", "$where": "vigenciadesde >= '2017-12-01'"}
    ).raise_for_status().json()
    frame = pd.DataFrame(rows)
    frame["valor"] = pd.to_numeric(frame["valor"])
    frame["desde"] = pd.to_datetime(frame["vigenciadesde"]).dt.normalize()
    frame["hasta"] = pd.to_datetime(frame["vigenciahasta"]).dt.normalize()
    days: dict[pd.Timestamp, float] = {}
    for row in frame.itertuples():
        for day in pd.date_range(row.desde, row.hasta, freq="D"):
            days[day] = float(row.valor)
    return pd.Series(days).sort_index().rename("trm")


def fetch_brent(client: httpx.Client) -> pd.Series:
    text = client.get(BRENT_URL).raise_for_status().text
    frame = pd.read_csv(io.StringIO(text), na_values=["."], parse_dates=["observation_date"])
    series = frame.set_index("observation_date")["DCOILBRENTEU"].dropna().astype(float)
    return series.rename("brent")


def main() -> None:
    with httpx.Client(timeout=60.0) as client:
        trm, brent = fetch_trm(client), fetch_brent(client)
    index = pd.date_range(START, max(trm.index.max(), brent.index.max()), freq="D")
    frame = pd.DataFrame({"trm": trm.reindex(index).ffill(), "brent": brent.reindex(index).ffill()})
    frame.index.name = "day"
    frame.to_csv(OUT)
    print(f"saved {frame.shape} -> {OUT}")
    print(f"trm   first {trm.index.min().date()} last {trm.index.max().date()} ({len(trm)} days)")
    print(f"brent first {brent.index.min().date()} last {brent.index.max().date()} ({len(brent)} days)")
    print(frame.describe().round(2).to_string())


if __name__ == "__main__":
    main()
