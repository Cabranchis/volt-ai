-- Volt-AI schema. Portable between PostgreSQL (production) and SQLite (tests, local dev).
-- Rules: no provider-specific features here; PostgreSQL-only statements go in *.pg.sql files.

-- Daily values in long format. Series names are listed in docs/data-dictionary.md.
CREATE TABLE series_daily (
    series TEXT NOT NULL,
    day DATE NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (series, day)
);

-- Hourly values, kept only for the recent past (see ADR 0005). Hour is 1..24 as published by XM.
CREATE TABLE series_hourly (
    series TEXT NOT NULL,
    day DATE NOT NULL,
    hour SMALLINT NOT NULL CHECK (hour BETWEEN 1 AND 24),
    value DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (series, day, hour)
);

-- One row per training run, with backtest metrics for the model and its baselines.
CREATE TABLE model_runs (
    run_id TEXT PRIMARY KEY,
    trained_at TIMESTAMP NOT NULL,
    data_start DATE NOT NULL,
    data_end DATE NOT NULL,
    metrics JSON NOT NULL,
    params JSON NOT NULL
);

-- Quantile forecasts. drivers holds the top SHAP contributions of the P50 forecast.
CREATE TABLE forecasts (
    run_id TEXT NOT NULL REFERENCES model_runs (run_id),
    target TEXT NOT NULL,
    day DATE NOT NULL,
    horizon SMALLINT NOT NULL CHECK (horizon >= 1),
    p10 DOUBLE PRECISION NOT NULL,
    p50 DOUBLE PRECISION NOT NULL,
    p90 DOUBLE PRECISION NOT NULL,
    drivers JSON,
    PRIMARY KEY (run_id, target, day),
    CHECK (p10 <= p50 AND p50 <= p90)
);

CREATE TABLE anomalies (
    target TEXT NOT NULL,
    day DATE NOT NULL,
    severity DOUBLE PRECISION NOT NULL CHECK (severity >= 0),
    direction TEXT NOT NULL CHECK (direction IN ('high', 'low')),
    method TEXT NOT NULL,
    detail JSON,
    PRIMARY KEY (target, day)
);

CREATE TABLE briefings (
    day DATE NOT NULL,
    lang TEXT NOT NULL CHECK (lang IN ('es', 'en')),
    body TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('gemini', 'template')),
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (day, lang)
);

-- Sliding-window counters for the chat endpoint. The web role may write only here.
CREATE TABLE rate_limits (
    client_key TEXT NOT NULL,
    window_start BIGINT NOT NULL,
    hits INTEGER NOT NULL,
    PRIMARY KEY (client_key, window_start)
);

-- Freshness per dataset, read by /api/v1/health.
CREATE TABLE ingest_log (
    dataset TEXT PRIMARY KEY,
    last_day DATE,
    updated_at TIMESTAMP NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'error')),
    detail TEXT
);

CREATE INDEX idx_series_daily_day ON series_daily (day);
CREATE INDEX idx_forecasts_target_day ON forecasts (target, day);
CREATE INDEX idx_model_runs_trained_at ON model_runs (trained_at);
