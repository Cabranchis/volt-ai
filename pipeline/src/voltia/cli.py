"""Command line entry point: `voltia <command>`."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo

import pandas as pd
import structlog
import typer
from sqlalchemy import Engine

from voltia import db
from voltia.anomalies import detect_all
from voltia.briefing import LANGS, build_facts, polish, template
from voltia.config import Settings, get_settings
from voltia.features import TARGETS
from voltia.forecast import TrainedTarget, forecast_target, load_models, save_models
from voltia.forecast import train as train_models
from voltia.ingest import DATASETS, OPTIONAL_DATASETS, Clients, Result, run_all
from voltia.models.backtest import BacktestConfig
from voltia.models.gbm import GBMParams
from voltia.sources.oni import OniClient
from voltia.sources.openmeteo import OpenMeteoClient
from voltia.sources.xm import XMClient

app = typer.Typer(help="Volt-AI data pipeline", no_args_is_help=True, add_completion=False)
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
        mark = "ok   " if r.ok else ("warn " if r.dataset in OPTIONAL_DATASETS else "FAIL ")
        extra = "" if r.ok else r.detail
        typer.echo(f"{mark}{r.dataset:<14} rows={r.rows:<8} last_day={r.last_day} {extra}")
        if not r.ok and r.dataset in OPTIONAL_DATASETS:
            # GitHub Actions shows this on the run summary; the job itself still succeeds.
            typer.echo(f"::warning::optional dataset {r.dataset} failed: {r.detail}")
    if any(not r.ok and r.dataset not in OPTIONAL_DATASETS for r in results):
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


def _history(engine: Engine) -> pd.DataFrame:
    history = db.read_series(engine)
    missing = [t for t in TARGETS if t not in history.columns]
    if history.empty or missing:
        typer.echo(f"no data for {', '.join(missing) or 'any series'}; run `voltia backfill` first")
        raise typer.Exit(code=1)
    return history


def _write_forecasts(
    engine: Engine,
    settings: Settings,
    history: pd.DataFrame,
    run_id: str,
    models: dict[str, TrainedTarget],
) -> None:
    frame = pd.concat([forecast_target(history, m) for m in models.values()], ignore_index=True)
    db.upsert_forecasts(engine, run_id, frame, keep_runs=settings.keep_forecast_runs)
    for target, part in frame.groupby("target", sort=False):
        first, last = part.iloc[0], part.iloc[-1]
        typer.echo(
            f"forecast {target:<19} {first['day'].date()}..{last['day'].date()} "
            f"day1 p50={first['p50']:.4g} [{first['p10']:.4g}, {first['p90']:.4g}]  "
            f"top driver: {first['drivers'][0]['feature']}"
        )
    typer.echo(f"wrote {len(frame)} forecast rows for run {run_id}")


def _train_summary(metrics: dict[str, Any]) -> None:
    for target, m in metrics["targets"].items():
        o = m["overall"]
        calibrated = m["coverage"]["calibrated"]
        shown = "n/a" if calibrated is None else f"{calibrated:.2f}"
        typer.echo(
            f"{target:<19} origins={m['n_origins']} MASE model={o['model']['mase']:.3f} "
            f"seasonal_naive={o['seasonal_naive']['mase']:.3f} ets={o['ets']['mase']:.3f} | "
            f"P10-P90 coverage raw={m['coverage']['raw']:.2f} "
            f"calibrated={shown} (nominal 0.80)"
        )


@app.command()
def train(
    predict: Annotated[bool, typer.Option("--predict", help="Also write forecasts")] = False,
    origins: Annotated[
        int | None, typer.Option(help="Last N origins instead of the fixed calendar")
    ] = None,
    warmup: Annotated[int | None, typer.Option(help="Calibration warm-up origins")] = None,
    step: Annotated[int | None, typer.Option(help="Days between origins")] = None,
    rounds: Annotated[int | None, typer.Option(help="Boosting rounds (smoke runs)")] = None,
) -> None:
    """Backtest, fit and store the forecasters, and record the run in model_runs."""
    settings = get_settings()
    engine = _engine(settings)
    history = _history(engine)
    cfg = BacktestConfig()
    cfg = replace(
        cfg,
        n_origins=origins or cfg.n_origins,
        anchor=None if origins else cfg.anchor,
        n_warmup=cfg.n_warmup if warmup is None else warmup,
        step_days=step or cfg.step_days,
    )
    params = GBMParams(num_threads=settings.ml_threads)
    if rounds:
        params = replace(params, num_boost_round=rounds)
    result = train_models(history, params, cfg)
    db.insert_model_run(
        engine,
        result.run_id,
        result.trained_at,
        result.data_start,
        result.data_end,
        result.metrics,
        result.params,
    )
    save_models(settings.voltia_models_dir, result)
    _train_summary(result.metrics)
    typer.echo(
        f"run {result.run_id} data {result.data_start}..{result.data_end} "
        f"trained in {result.seconds:.0f} s"
    )
    if predict:
        _write_forecasts(engine, settings, history, result.run_id, result.models)


@app.command()
def predict() -> None:
    """Forecast from the latest settled day with the stored models (no retraining)."""
    settings = get_settings()
    engine = _engine(settings)
    try:
        run_id, models = load_models(settings.voltia_models_dir)
    except FileNotFoundError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    if not db.run_exists(engine, run_id):
        typer.echo(f"run {run_id} is not in model_runs; run `voltia train` on this database")
        raise typer.Exit(code=1)
    _write_forecasts(engine, settings, _history(engine), run_id, models)


@app.command()
def anomalies() -> None:
    """Detect atypical days for demand and price and replace the anomalies table rows."""
    engine = _engine(get_settings())
    history = _history(engine)
    frame = detect_all(history, tuple(TARGETS))
    db.upsert_anomalies(engine, frame, targets=TARGETS)
    for target in TARGETS:
        part = frame[frame["target"] == target]
        days = int(history[target].notna().sum())
        typer.echo(f"{target:<19} flagged {len(part)} of {days} days ({len(part) / days:.1%})")
        top = part.nlargest(3, "severity")
        for day, direction, severity, detail in zip(
            top["day"], top["direction"], top["severity"], top["detail"], strict=True
        ):
            typer.echo(
                f"  {pd.Timestamp(day).date()} {direction:<4} severity={severity:.1f} "
                f"deviation={detail['deviation_pct']:+.1f}%"
            )


@app.command()
def brief(
    model: Annotated[str, typer.Option(help="Gemini model used to polish the text")] = (
        "gemini-flash-lite-latest"
    ),
) -> None:
    """Write today's briefing (ES and EN). Uses Gemini if a key is set, else the template."""
    settings = get_settings()
    engine = _engine(settings)
    history = db.read_series(engine)
    next_week: float | None = None
    with engine.connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT f.p50 FROM forecasts f JOIN model_runs r ON r.run_id = f.run_id "
            "WHERE f.target = 'demand_kwh' AND f.horizon = 7 "
            "ORDER BY r.trained_at DESC LIMIT 1"
        ).first()
        if row is not None:
            next_week = float(row[0])
    facts = build_facts(history, next_week)
    if facts is None:
        typer.echo("no demand data; run `voltia backfill` first")
        raise typer.Exit(code=1)
    rows: dict[str, tuple[str, str]] = {}
    for lang in LANGS:
        text = template(facts, lang)
        polished = None
        if settings.google_generative_ai_api_key:
            polished = polish(text, lang, settings.google_generative_ai_api_key, model)
        rows[lang] = (polished, "gemini") if polished else (text, "template")
        typer.echo(f"[{lang}] ({rows[lang][1]}) {rows[lang][0]}")
    db.upsert_briefings(engine, facts.day, rows)


if __name__ == "__main__":
    app()
