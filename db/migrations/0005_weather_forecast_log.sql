-- Weather forecasts as Open-Meteo issued them on each day, for the 16 days ahead, at the demand
-- centres and near the main reservoirs. The weather series only holds what happened; a forecast
-- cannot be rebuilt later, so it is stored from today on and never rewritten. Evaluating whether
-- rain forecasts help the price model needs a few months of this log.
CREATE TABLE weather_forecast_log (
    issued DATE NOT NULL,
    location TEXT NOT NULL,
    day DATE NOT NULL,
    lead_days SMALLINT NOT NULL CHECK (lead_days >= 0),
    model TEXT NOT NULL,
    fetched_at TIMESTAMP NOT NULL,
    precip_mm DOUBLE PRECISION NOT NULL,
    temp_c DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (issued, location, day)
);

CREATE INDEX idx_weather_forecast_log_day ON weather_forecast_log (day);
