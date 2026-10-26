-- Daily values per reservoir and per river, as XM publishes them (docs/data-dictionary.md).
-- Kept apart from series_daily, which holds one value per day for the whole system.
CREATE TABLE entity_daily (
    metric TEXT NOT NULL,
    entity TEXT NOT NULL,
    day DATE NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (metric, entity, day)
);

-- Which hydrological region each reservoir and river belongs to, replaced on every ingest.
CREATE TABLE entity_catalog (
    kind TEXT NOT NULL CHECK (kind IN ('reservoir', 'river')),
    entity TEXT NOT NULL,
    region TEXT NOT NULL,
    PRIMARY KEY (kind, entity)
);

CREATE INDEX idx_entity_daily_day ON entity_daily (day);
