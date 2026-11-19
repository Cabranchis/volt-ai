"""Why does the live demand range cover less than the 80 % it promises?

The Models page shows the live record: 62 to 70 % of the demand forecasts of 4 to 30 days fell inside
the P10-P90 range, against 80 % promised and 78 to 84 % in the backtest. This script reads the live
record (forecast_log, as first issued) and asks whether the misses are spread over the weeks, which
would point at a band that is too narrow, or concentrated in some days, which would point at an
event the forecast could not see.

Inputs: the weekly backup (`voltia archive`, the workflow artifact `volt-ai-backup`, which holds
forecast_log.csv.gz) and the real demand from the public API. It reads files and one public URL;
it never touches the database.

    gh run download <weekly backup run> -n volt-ai-backup -D <empty folder>
    uv run python research/run_live_demand.py <that folder>

No decision rule: it is a diagnosis. It proposes no change to the model. Writes
research/results/live_demand_coverage.json.
"""

from __future__ import annotations

import gzip
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
OUT = HERE / "results" / "live_demand_coverage.json"
SITE = "https://voltia-xi-five.vercel.app/api/v1/series"
BUCKETS = (("1-3", 1, 3), ("4-7", 4, 7), ("8-14", 8, 14), ("15-30", 15, 30))


def real_demand(first: str, last: str) -> pd.Series:
    with urllib.request.urlopen(f"{SITE}?names=demand_kwh&from={first}&to={last}", timeout=30) as response:  # noqa: S310
        data = json.load(response)
    return pd.Series(data["series"]["demand_kwh"], index=pd.to_datetime(data["dates"])).dropna()


def evaluated(backup: Path) -> pd.DataFrame:
    with gzip.open(backup / "forecast_log.csv.gz", "rt", encoding="utf-8") as handle:
        log = pd.read_csv(handle)
    log = log[log["target"] == "demand_kwh"].copy()
    log["day"] = pd.to_datetime(log["day"])
    actual = real_demand(str(log["day"].min().date()), str(log["day"].max().date()))
    log["actual"] = log["day"].map(actual)
    rows = log.dropna(subset=["actual"]).copy()
    rows["inside"] = (rows["actual"] >= rows["p10"]) & (rows["actual"] <= rows["p90"])
    rows["below"] = rows["actual"] < rows["p10"]
    rows["above"] = rows["actual"] > rows["p90"]
    rows["error_pct"] = (rows["p50"] - rows["actual"]) / rows["actual"] * 100
    return rows


def summary(frame: pd.DataFrame) -> dict[str, float]:
    return {
        "forecasts": int(len(frame)),
        "inside": round(float(frame["inside"].mean()), 3),
        "below_p10": round(float(frame["below"].mean()), 3),
        "above_p90": round(float(frame["above"].mean()), 3),
        "mean_error_pct": round(float(frame["error_pct"].mean()), 2),
        "mean_abs_error_pct": round(float(frame["error_pct"].abs().mean()), 2),
    }


def main(backup: Path) -> None:
    rows = evaluated(backup)
    first = rows["day"].min()
    rows["week"] = ((rows["day"] - first).dt.days // 7).map(lambda w: f"{(first + pd.Timedelta(days=7 * int(w))).date()}")
    by_bucket = {name: summary(rows[rows["horizon"].between(low, high)]) for name, low, high in BUCKETS}
    by_week = {week: {**summary(part), "target_days": int(part["day"].nunique())} for week, part in rows.groupby("week")}
    by_week_bucket = {
        week: {
            name: round(float(part[part["horizon"].between(low, high)]["inside"].mean()), 3)
            for name, low, high in BUCKETS
            if part["horizon"].between(low, high).any()
        }
        for week, part in rows.groupby("week")
    }
    out = {
        "source": "forecast_log (as first issued) and the public series API",
        "target_days": f"{rows['day'].min().date()} to {rows['day'].max().date()}",
        "forecasts": int(len(rows)),
        "origins": int(rows["origin"].nunique()),
        "all": summary(rows),
        "by_horizon": by_bucket,
        "by_week_of_the_target_day": by_week,
        "inside_by_week_and_horizon": by_week_bucket,
    }
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    assert np.isfinite(out["all"]["inside"])  # type: ignore[arg-type,index]


if __name__ == "__main__":
    main(Path(sys.argv[1]))
