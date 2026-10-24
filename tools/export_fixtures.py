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


def main() -> None:
    copy_feature_labels()
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

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
