-- Permanent record of every forecast as it was first issued. `forecasts` keeps only the latest runs
-- (it feeds the site); this table is never pruned or rewritten, so forecasts can be scored against
-- what happened later. origin is the last settled day when the forecast was made (day - horizon).
CREATE TABLE forecast_log (
    target TEXT NOT NULL,
    origin DATE NOT NULL,
    day DATE NOT NULL,
    horizon SMALLINT NOT NULL CHECK (horizon >= 1),
    run_id TEXT NOT NULL,
    issued_at TIMESTAMP NOT NULL,
    p10 DOUBLE PRECISION NOT NULL,
    p50 DOUBLE PRECISION NOT NULL,
    p90 DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (target, origin, day),
    CHECK (p10 <= p50 AND p50 <= p90)
);

CREATE INDEX idx_forecast_log_target_day ON forecast_log (target, day);
