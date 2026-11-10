"""Pack the El Nino case study for the web page: regime scores, four cases, monthly context.

Reads `results/case_el_nino_rows.json` (from case_el_nino.py), the production metrics and the local
SQLite copy of the data; writes `web/src/lib/case-study/el-nino.json`. Only origins whose 14-day
horizon is fully observed are scored, as in production.

    DATABASE_URL=sqlite:///data/voltia.sqlite uv run python research/case_el_nino_pack.py
"""

from __future__ import annotations

import json
import statistics as st
import urllib.request
from pathlib import Path

import pandas as pd

from voltia import db

HERE = Path(__file__).parent
OUT = HERE.parents[1] / "web" / "src" / "lib" / "case-study" / "el-nino.json"
API = "https://voltia-xi-five.vercel.app/api/v1/model"
# Examples among the origins where the model beat both references (31 of 50); the page says so.
CASES = ["2024-01-02", "2025-01-14", "2026-06-23", "2026-09-15"]
HISTORY_DAYS = 21
REGIMES = [
    ("nino-2023", "2023-11-01", "2024-04-30"),
    ("shock-2024", "2024-05-01", "2024-12-31"),
    ("calm", "2025-01-01", "2026-06-30"),
    ("nino-2026", "2026-07-01", "2026-12-31"),
    ("all", "2000-01-01", "2999-01-01"),
]
MONTHS = ["2023-10", "2023-12"]
ONI_LAG_DAYS = 75  # the index of a month is published about two months later (features.py)


def mape(day_rows: list[dict], key: str) -> float:
    scored = [r for r in day_rows if r["y"]]
    return round(100 * st.mean(abs(r[key] - r["y"]) / r["y"] for r in scored), 1)


def main() -> None:
    model = json.load(urllib.request.urlopen(API))
    by_origin = model["metrics"]["targets"]["price_mean_cop_kwh"]["by_origin"]
    regimes = {}
    for key, lo, hi in REGIMES:
        part = [o for o in by_origin if lo <= o["origin"] <= hi]
        regimes[key] = {
            "origins": len(part),
            "model": round(st.mean(o["model_mase"] for o in part), 2),
            "ets": round(st.mean(o["ets_mase"] for o in part), 2),
            "naive": round(st.mean(o["seasonal_naive_mase"] for o in part), 2),
            "coverage": round(st.mean(o["model_coverage"] for o in part), 2),
            "won": sum(o["model_mase"] < min(o["ets_mase"], o["seasonal_naive_mase"]) for o in part),
        }

    stored = json.loads((HERE / "results" / "case_el_nino_rows.json").read_text())
    # The origins are anchored to the calendar, so a new daily run does not change their scores:
    # the stored rows must still match production, origin by origin.
    prod_mase = {o["origin"]: o["model_mase"] for o in by_origin}
    off = [o["origin"] for o in stored["origins"] if o["origin"] in prod_mase and abs(o["mase"] - prod_mase[o["origin"]]) > 1e-3]
    if off:
        raise SystemExit(f"stored rows differ from production on {off}: re-run case_el_nino.py")
    rows = {o["origin"]: o["rows"] for o in stored["origins"]}
    hist = db.read_series(db.make_engine())
    cases = []
    for origin in CASES:
        end = pd.Timestamp(origin)
        past = hist.loc[end - pd.Timedelta(days=HISTORY_DAYS) : end, "price_mean_cop_kwh"].dropna()
        score = next(o for o in by_origin if o["origin"] == origin)
        cases.append({
            "origin": origin,
            "scores": {
                "model": score["model_mase"], "ets": score["ets_mase"],
                "naive": score["seasonal_naive_mase"], "coverage": score["model_coverage"],
                "mapeModel": mape(rows[origin], "p50"), "mapeEts": mape(rows[origin], "ets"),
            },
            "history": [{"day": str(d.date()), "y": round(float(v), 1)} for d, v in past.items()],
            "rows": [
                {"day": r["day"], "y": None if r["y"] is None else round(r["y"], 1),
                 "p10": round(r["p10"], 1), "p50": round(r["p50"], 1), "p90": round(r["p90"], 1), "ets": round(r["ets"], 1)}
                for r in rows[origin]
            ],
        })

    h = hist.copy()
    oni_stored = h["oni"].dropna()
    months = {}
    for m in MONTHS:
        part = h.loc[m]
        end = part.index[-1]
        known = oni_stored[oni_stored.index <= end - pd.Timedelta(days=ONI_LAG_DAYS)]
        both = part[["gen_thermal_kwh", "gen_total_kwh"]].dropna()
        months[m] = {
            "price": round(float(part["price_mean_cop_kwh"].mean()), 0),
            "reservoirMin": round(float(part["reservoir_pct"].min()) * 100, 1),
            "inflows": round(float(part["inflows_pct"].mean()) * 100, 0),
            "thermal": round(float(both["gen_thermal_kwh"].sum() / both["gen_total_kwh"].sum() * 100), 1),
            "oni": round(float(known.iloc[-1]), 2),
        }

    targets = model["metrics"]["targets"]
    overall = {
        name: {
            "mape": round(targets[key]["overall"]["model"]["mape"], 1),
            "etsMape": round(targets[key]["overall"]["ets"]["mape"], 1),
            "coverage": round(targets[key]["overall"]["model"]["coverage_p10_p90"], 3),
            "origins": targets[key]["n_origins"],
        }
        for name, key in (("demand", "demand_kwh"), ("price", "price_mean_cop_kwh"))
    }
    payload = {"overall": overall, "runId": model["runId"], "dataEnd": model["dataEnd"], "regimes": regimes, "cases": cases, "months": months}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, separators=(",", ":")))
    print("wrote", OUT, OUT.stat().st_size, "bytes")
    print(json.dumps({"regimes": regimes, "months": months}, indent=1))


if __name__ == "__main__":
    main()
