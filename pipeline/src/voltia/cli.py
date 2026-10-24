"""Command line entry point: `voltia <command>`."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

import structlog
import typer
from sqlalchemy import Engine

from voltia import db
from voltia.config import Settings, get_settings
from voltia.ingest import DATASETS, Clients, Result, run_all
from voltia.sources.oni import OniClient
from voltia.sources.openmeteo import OpenMeteoClient
from voltia.sources.xm import XMClient

app = typer.Typer(help="VoltIA data pipeline", no_args_is_help=True, add_completion=False)
log = structlog.get_logger()

BOGOTA = ZoneInfo("America/Bogota")


def today_bogota() -> date:
    """Today in Colombia (UTC-5, no daylight saving), which is what XM publishes by."""
    return datetime.now(BOGOTA).date()


def _engine(settings: Settings) -> Engine:
    engine = db.make_engine(settings.resolved_database_url)
    db.migrate(engine)
    return engine


def _run(settings: Settings, since: date, full: bool, only: list[str] | None) -> list[Result]:
    engine = _engine(settings)
    xm = XMClient(settings.xm_base_url, settings.http_timeout_s)
    meteo = OpenMeteoClient()
    oni = OniClient()
    try:
        return run_all(engine, Clients(xm, meteo, oni), settings, since, today_bogota(), full, only)
    finally:
        xm.close()
        meteo.close()
        oni.close()


def _report(results: list[Result]) -> None:
    for r in results:
        mark = "ok   " if r.ok else "FAIL "
        extra = "" if r.ok else r.detail
        typer.echo(f"{mark}{r.dataset:<14} rows={r.rows:<8} last_day={r.last_day} {extra}")
    if any(not r.ok for r in results):
        raise typer.Exit(code=1)


Only = Annotated[
    list[str] | None,
    typer.Option("--only", help=f"Restrict to datasets: {', '.join(DATASETS)}"),
]


@app.command()
def migrate() -> None:
    """Create or upgrade the database schema."""
    applied = db.migrate(db.make_engine(get_settings().resolved_database_url))
    typer.echo("applied: " + (", ".join(applied) if applied else "nothing to do"))


@app.command()
def backfill(
    since: Annotated[str | None, typer.Option(help="First day, YYYY-MM-DD")] = None,
    only: Only = None,
) -> None:
    """Load the full history from `since` (default 2018-01-01). Slow the first time."""
    settings = get_settings()
    start = date.fromisoformat(since or settings.history_start)
    _report(_run(settings, start, full=True, only=only))


@app.command()
def update(only: Only = None) -> None:
    """Fetch what is new since the last run, re-reading the last days XM may have revised."""
    settings = get_settings()
    _report(_run(settings, date.fromisoformat(settings.history_start), full=False, only=only))


@app.command()
def status() -> None:
    """Show row counts and the freshness of each dataset."""
    engine = _engine(get_settings())
    counts = db.table_counts(engine, ["series_daily", "series_hourly", "forecasts", "anomalies"])
    for name, n in counts.items():
        typer.echo(f"{name:<14} {n}")
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT dataset, last_day, status, updated_at FROM ingest_log ORDER BY dataset"
        ).all()
    for dataset, last_day, st, updated in rows:
        typer.echo(f"{dataset:<14} last_day={last_day} status={st} updated={updated}")


if __name__ == "__main__":
    app()
