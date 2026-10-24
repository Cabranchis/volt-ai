"""Database access: engine, migrations and idempotent writes (SQLAlchemy Core).

The same code runs on PostgreSQL (production) and SQLite (tests and local development).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import Engine, MetaData, Table, create_engine, delete, event, select, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import Connection

from voltia.config import MIGRATIONS_DIR, get_settings

_BATCH = 5_000


def make_engine(url: str | None = None) -> Engine:
    """Create an engine. SQLite connections enforce foreign keys."""
    engine = create_engine(url or get_settings().resolved_database_url, future=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn: Any, _record: Any) -> None:
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def utcnow() -> datetime:
    """Naive UTC timestamp, the convention for TIMESTAMP columns in this schema."""
    return datetime.now(UTC).replace(tzinfo=None)


def _statements(sql: str) -> list[str]:
    """Split a migration into statements. Semicolons inside $$ ... $$ blocks do not split."""
    no_comments = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    statements: list[str] = []
    current: list[str] = []
    in_dollar = False
    i = 0
    while i < len(no_comments):
        if no_comments.startswith("$$", i):
            in_dollar = not in_dollar
            current.append("$$")
            i += 2
            continue
        char = no_comments[i]
        if char == ";" and not in_dollar:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        i += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def migrate(engine: Engine) -> list[str]:
    """Apply pending migrations in order and return the versions applied now."""
    applied_now: list[str] = []
    is_pg = engine.dialect.name == "postgresql"
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
        )
        done = {row[0] for row in conn.exec_driver_sql("SELECT version FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            pg_only = path.name.endswith(".pg.sql")
            version = path.name.removesuffix(".sql")
            if version in done or (pg_only and not is_pg):
                continue
            sql = path.read_text(encoding="utf-8")
            for stmt in _statements(sql):
                conn.exec_driver_sql(stmt)
            conn.execute(
                text("INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :t)"),
                {"v": version, "t": utcnow()},
            )
            applied_now.append(version)
    return applied_now


def _table(conn: Connection, name: str) -> Table:
    return Table(name, MetaData(), autoload_with=conn)


def _upsert(
    conn: Connection,
    name: str,
    rows: list[dict[str, Any]],
    keys: list[str],
) -> int:
    """Insert rows, replacing non-key columns on conflict. Returns the number of rows sent."""
    if not rows:
        return 0
    table = _table(conn, name)
    insert_fn = postgresql.insert if conn.dialect.name == "postgresql" else sqlite.insert
    stmt = insert_fn(table)
    update_cols = {c.name: stmt.excluded[c.name] for c in table.columns if c.name not in keys}
    stmt = stmt.on_conflict_do_update(index_elements=keys, set_=update_cols)
    for i in range(0, len(rows), _BATCH):
        conn.execute(stmt, rows[i : i + _BATCH])
    return len(rows)


def upsert_series_daily(engine: Engine, frame: pd.DataFrame) -> int:
    """Upsert a long frame with columns series, day (date) and value."""
    rows = [
        {"series": str(s), "day": d, "value": float(v)}
        for s, d, v in zip(frame["series"], _as_dates(frame["day"]), frame["value"], strict=True)
    ]
    with engine.begin() as conn:
        return _upsert(conn, "series_daily", rows, ["series", "day"])


def upsert_series_hourly(engine: Engine, frame: pd.DataFrame) -> int:
    """Upsert a long frame with columns series, day (date), hour (1..24) and value."""
    rows = [
        {"series": str(s), "day": d, "hour": int(h), "value": float(v)}
        for s, d, h, v in zip(
            frame["series"], _as_dates(frame["day"]), frame["hour"], frame["value"], strict=True
        )
    ]
    with engine.begin() as conn:
        return _upsert(conn, "series_hourly", rows, ["series", "day", "hour"])


def prune_hourly(engine: Engine, today: date, keep_days: int) -> int:
    """Delete hourly rows older than keep_days. Returns the number removed."""
    cutoff = today - timedelta(days=keep_days)
    with engine.begin() as conn:
        table = _table(conn, "series_hourly")
        result = conn.execute(delete(table).where(table.c.day < cutoff))
        return int(result.rowcount or 0)


def _as_dates(values: Iterable[Any]) -> list[date]:
    return [pd.Timestamp(v).date() for v in values]


def log_ingest(
    engine: Engine, dataset: str, last_day: date | None, status: str, detail: str | None = None
) -> None:
    """Record the outcome of an ingest. On error the previous last_day is kept."""
    with engine.begin() as conn:
        previous = get_last_day(engine, dataset, conn)
        row = {
            "dataset": dataset,
            "last_day": last_day if status == "ok" else previous,
            "updated_at": utcnow(),
            "status": status,
            "detail": detail,
        }
        _upsert(conn, "ingest_log", [row], ["dataset"])


def get_last_day(engine: Engine, dataset: str, conn: Connection | None = None) -> date | None:
    def run(c: Connection) -> date | None:
        table = _table(c, "ingest_log")
        row = c.execute(select(table.c.last_day).where(table.c.dataset == dataset)).first()
        return row[0] if row else None

    if conn is not None:
        return run(conn)
    with engine.connect() as c:
        return run(c)


def read_series(engine: Engine, series: Iterable[str] | None = None) -> pd.DataFrame:
    """Return daily series as a wide frame indexed by day (DatetimeIndex), one column per series."""
    with engine.connect() as conn:
        table = _table(conn, "series_daily")
        stmt = select(table.c.series, table.c.day, table.c.value)
        if series is not None:
            stmt = stmt.where(table.c.series.in_(list(series)))
        rows = conn.execute(stmt).all()
    if not rows:
        return pd.DataFrame()
    long = pd.DataFrame(rows, columns=["series", "day", "value"])
    long["day"] = pd.to_datetime(long["day"])
    wide = long.pivot(index="day", columns="series", values="value").sort_index()
    wide.columns.name = None
    return wide


def table_counts(engine: Engine, names: Iterable[str]) -> Mapping[str, int]:
    safe = [n for n in names if re.fullmatch(r"[a-z_]+", n)]
    out: dict[str, int] = {}
    with engine.connect() as conn:
        for name in safe:
            out[name] = int(conn.exec_driver_sql(f"SELECT COUNT(*) FROM {name}").scalar_one())  # noqa: S608
    return out
