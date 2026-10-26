"""Export the local SQLite database as JSON fixtures for the web app (ADR 0008).

Run with the pipeline interpreter, from the repository root:

    pipeline/.venv/Scripts/python.exe -I tools/export_fixtures.py

Reads pipeline/data/voltia.sqlite (or the path in argv[1]) and writes web/src/lib/data/fixtures/.
Only the standard library is used, so it works without installing the pipeline package.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "pipeline" / "data" / "voltia.sqlite"
OUT = ROOT / "web" / "src" / "lib" / "data" / "fixtures"


def rounded(value: float) -> float:
    """Keep fixtures small: 2 decimals is far below the precision of any chart."""
    return round(value, 2) if abs(value) >= 10 else round(value, 4)


def write(name: str, payload: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"{name:<18} {path.stat().st_size / 1024:8.1f} KiB")


def load_json(text: str | None) -> object:
    return json.loads(text) if text else None


def copy_feature_labels() -> None:
    """The pipeline owns the plain-language names of model features; the web app shows them."""
    source = ROOT / "pipeline" / "src" / "voltia" / "feature_labels.json"
    if source.exists():
        write("feature-labels.json", json.loads(source.read_text(encoding="utf-8")))


REGIONAL_HISTORY_DAYS = 365


def export_regional(conn: sqlite3.Connection) -> None:
    """Latest reservoirs and the by-region history of the map page (RegionalData in the web app)."""
    last = conn.execute(
        "SELECT MAX(day) FROM entity_daily WHERE metric = 'reservoir_kwh'"
    ).fetchone()[0]
    if last is None:
        write("regional.json", None)
        return
    reservoirs = [
        {
            "name": r["name"],
            "region": r["region"],
            "volumeKwh": r["volume"],
            "capacityKwh": r["capacity"],
            "weekAgoKwh": r["week_ago"],
        }
        for r in conn.execute(
            """
            SELECT c.entity AS name, c.region, v.value AS volume, k.value AS capacity, w.value AS week_ago
            FROM entity_daily v
            JOIN entity_catalog c ON c.kind = 'reservoir' AND c.entity = v.entity
            JOIN entity_daily k ON k.metric = 'reservoir_capacity_kwh' AND k.entity = v.entity AND k.day = v.day
            LEFT JOIN entity_daily w ON w.metric = 'reservoir_kwh' AND w.entity = v.entity
                 AND w.day = date(v.day, '-7 day')
            WHERE v.metric = 'reservoir_kwh' AND v.day = ?
            ORDER BY c.entity
            """,
            (last,),
        )
    ]
    since = f"date(?, '-{REGIONAL_HISTORY_DAYS} day')"
    level = conn.execute(
        f"""
        SELECT c.region, v.day, SUM(v.value) / SUM(k.value) AS pct
        FROM entity_catalog c
        JOIN entity_daily v ON v.metric = 'reservoir_kwh' AND v.entity = c.entity
        JOIN entity_daily k ON k.metric = 'reservoir_capacity_kwh' AND k.entity = v.entity AND k.day = v.day
        WHERE c.kind = 'reservoir' AND v.day > {since}
        GROUP BY c.region, v.day
        """,
        (last,),
    ).fetchall()
    inflow = conn.execute(
        f"""
        SELECT c.region, a.day, SUM(a.value) / SUM(h.value) AS pct
        FROM entity_catalog c
        JOIN entity_daily a ON a.metric = 'inflows_kwh' AND a.entity = c.entity
        JOIN entity_daily h ON h.metric = 'inflows_hist_mean_kwh' AND h.entity = a.entity AND h.day = a.day
        WHERE c.kind = 'river' AND a.day > {since}
        GROUP BY c.region, a.day
        """,
        (last,),
    ).fetchall()
    dates = sorted({r["day"] for r in level} | {r["day"] for r in inflow})
    index = {d: i for i, d in enumerate(dates)}
    regions: dict[str, dict[str, list[float | None]]] = {}
    for key, rows in (("reservoirPct", level), ("inflowPct", inflow)):
        for r in rows:
            columns = regions.setdefault(
                r["region"],
                {"reservoirPct": [None] * len(dates), "inflowPct": [None] * len(dates)},
            )
            columns[key][index[r["day"]]] = round(r["pct"], 4)
    write(
        "regional.json",
        {"day": last, "reservoirs": reservoirs, "history": {"dates": dates, "regions": regions}},
    )


def main() -> None:
    copy_feature_labels()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    db_path = Path(args[0]) if args else DEFAULT_DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    export_regional(conn)
    if "--regional-only" in sys.argv:
        return

    rows = conn.execute("SELECT series, day, value FROM series_daily ORDER BY day").fetchall()
    dates = sorted({r["day"] for r in rows})
    index = {d: i for i, d in enumerate(dates)}
    series: dict[str, list[float | None]] = {}
    for r in rows:
        column = series.setdefault(r["series"], [None] * len(dates))
        column[index[r["day"]]] = rounded(r["value"])
    write("series.json", {"dates": dates, "series": dict(sorted(series.items()))})

    hourly = [
        {"series": r["series"], "day": r["day"], "hour": r["hour"], "value": rounded(r["value"])}
        for r in conn.execute(
            "SELECT series, day, hour, value FROM series_hourly "
            "WHERE day >= date((SELECT MAX(day) FROM series_hourly), '-13 day') ORDER BY day, hour"
        )
    ]
    write("hourly.json", hourly)

    run = conn.execute("SELECT * FROM model_runs ORDER BY trained_at DESC LIMIT 1").fetchone()
    model_run = (
        {
            "runId": run["run_id"],
            "trainedAt": run["trained_at"],
            "dataStart": run["data_start"],
            "dataEnd": run["data_end"],
            "metrics": load_json(run["metrics"]),
            "params": load_json(run["params"]),
        }
        if run
        else None
    )
    write("model-run.json", model_run)

    forecasts: dict[str, object] = {}
    if run:
        for target in ("demand_kwh", "price_mean_cop_kwh"):
            points = conn.execute(
                "SELECT day, horizon, p10, p50, p90, drivers FROM forecasts "
                "WHERE run_id = ? AND target = ? ORDER BY day",
                (run["run_id"], target),
            ).fetchall()
            if points:
                forecasts[target] = {
                    "runId": run["run_id"],
                    "target": target,
                    "trainedAt": run["trained_at"],
                    "points": [
                        {
                            "day": p["day"],
                            "horizon": p["horizon"],
                            "p10": p["p10"],
                            "p50": p["p50"],
                            "p90": p["p90"],
                            "drivers": load_json(p["drivers"]),
                        }
                        for p in points
                    ],
                }
    write("forecasts.json", forecasts)

    anomalies = [
        {
            "target": r["target"],
            "day": r["day"],
            "severity": r["severity"],
            "direction": r["direction"],
            "method": r["method"],
            "detail": load_json(r["detail"]),
        }
        for r in conn.execute("SELECT * FROM anomalies ORDER BY severity DESC")
    ]
    write("anomalies.json", anomalies)

    briefings = [
        {
            "day": r["day"],
            "lang": r["lang"],
            "body": r["body"],
            "source": r["source"],
            "createdAt": r["created_at"],
        }
        for r in conn.execute("SELECT * FROM briefings ORDER BY day DESC LIMIT 4")
    ]
    write("briefings.json", briefings)

    datasets = [
        {
            "dataset": r["dataset"],
            "lastDay": r["last_day"],
            "status": r["status"],
            "updatedAt": r["updated_at"],
            "detail": r["detail"],
        }
        for r in conn.execute("SELECT * FROM ingest_log ORDER BY dataset")
    ]
    freshness = [
        {"series": r["series"], "lastDay": r["last_day"]}
        for r in conn.execute(
            "SELECT series, MAX(day) AS last_day FROM series_daily GROUP BY series ORDER BY series"
        )
    ]
    write(
        "health.json",
        {
            "generatedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "datasets": datasets,
            "series": freshness,
        },
    )


if __name__ == "__main__":
    main()
