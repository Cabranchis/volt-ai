"""Download extra XM series the experiments may use, aggregated to one value per day.

Each series is saved with the last day XM had published when it was fetched, so the experiments
can model how late each one arrives (publication lag) instead of assuming it is known at once.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from voltia.sources.xm import XMClient

OUT = Path(__file__).parent / "data" / "extra.csv"
START = date(2018, 1, 1)

DAILY = {
    "PrecEsca": "scarcity_price",
    "PrecPromCont": "contract_price",
    "VertEner": "spill_kwh",
    "ENFICC": "enficc_kwh",
    "VolTurbMasa": "turbined_m3",
    "CapaUtilDiarEner": "reservoir_capacity_kwh",
    "DeltaNal": "delta_nal",
}
# metric -> (name, how the 24 hours collapse into one day)
HOURLY = {
    "MaxPrecOferNal": ("max_offer", "mean"),
    "CostMargDesp": ("dispatch_cost", "mean"),
    "ExpoEner": ("exports_kwh", "sum"),
    "ImpoEner": ("imports_kwh", "sum"),
    "PrecPromContNoRegu": ("contract_price_unreg", "mean"),
    "PrecBolsNaciTX1": ("price_tx1", "mean"),
}


def main() -> None:
    client = XMClient()
    end = date.today() + timedelta(days=2)
    columns: dict[str, pd.Series] = {}
    for metric, name in DAILY.items():
        df = client.daily_system(metric, START, end)
        columns[name] = df.groupby("day")["value"].mean()
        print(name, len(df), df["day"].max().date(), flush=True)
    for metric, (name, how) in HOURLY.items():
        df = client.hourly_system(metric, START, end)
        columns[name] = df.groupby("day")["value"].agg(how)
        if how == "mean":
            columns[name + "_max"] = df.groupby("day")["value"].max()
        print(name, len(df), df["day"].max().date(), flush=True)
    frame = pd.DataFrame(columns).sort_index()
    frame.to_csv(OUT, index_label="day")
    print(f"saved {frame.shape} -> {OUT}")


if __name__ == "__main__":
    main()
