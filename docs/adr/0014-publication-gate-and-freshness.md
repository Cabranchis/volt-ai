# ADR 0014: A publication gate, guards on every series and a health that reports age

Status: accepted (2026-11-15)

## Context
Volt-AI shows forecasts to people who decide with them, and `forecast_log` keeps every forecast for good. A review of the pipeline and the web app (2026-11-15) found that the platform was well protected against attackers (strict CSP, a read-only database role, a constant-time token, pinned actions) but not against its own data going wrong or stopping:

1. A forecast was stored whatever the backtest said. The comparison with the references was printed, not checked.
2. Only demand (ADR 0009) and hydrology (ADR 0013) had a plausibility check. Price, generation, contracts and market series only had fixed ranges that started at 0, so a price published in the wrong unit, or as 0, passed. The first day of a re-read batch was not compared with what was stored.
3. A source that renamed a field returned an empty frame for that series; the batch was accepted because another series had rows, and `ingest_log` said "ok" with a current date.
4. `/api/v1/health` said `degraded` only when a dataset had `status = error`. It ignored the age of the data, of the model and of the forecast, so a stopped pipeline looked healthy. Nobody was notified.

## Decision
Fail closed on what people decide with, fail open on availability: when something is doubtful the site keeps the last good forecast, says how old it is and tells the owner; it does not publish the doubtful one and it does not go down.

**The publication gate** (`voltia/gates.py`, called by `voltia train` and `voltia predict` before anything is written). A run is refused when, for either target: a forecast value is not finite or P10, P50, P90 are out of order; the forecast does not have its full horizon; the P50 of the price is outside 0.5 times the lowest to 1.5 times the highest price of the last 90 days (demand: outside its physical range); the model is worse than the weekly seasonal naive in the backtest; there are fewer than 40 test dates; the calibrated coverage of the 80 % range is outside 0.60 to 0.95; or the inputs are stale (price or demand more than 10 days, ONI more than 150, weather more than 30). A refused run exits with code 1, writes nothing and names the rules it failed. The limits come from the production backtest (51 dates; coverage 0.82 and 0.81; MASE 32 % and 42 % below the naive) and leave room for a bad month. `VOLTIA_GATE_MODE=warn`, a choice on the manual run of the workflow, publishes anyway after a person has read the problems.

**Guards on every series.** `drop_implausible_days` generalises ADR 0013: each guarded series is compared with its last accepted day and dropped, with the others of its group and its hourly rows, when the ratio is outside limits measured on 3 218 days (the mean price moved between 0.37 and 2.74 times in a day, the maximum price between 0.13 and 7.67; the limits are 0.1 to 8 and 0.05 to 20). The comparison also uses the last value stored before the batch (`db.last_values`), so a bad first day of a re-read cannot overwrite a good one. A reference older than 3 days is not used: a level that really changed is held back for those days and then accepted, so a guard cannot freeze a series. The floors of the schema are now above zero for prices and costs (a third of the lowest value in 2018-2026).

**Complete batches.** Each dataset lists the series it must bring (`REQUIRED_SERIES`); a missing series fails the batch and `ingest_log.last_day` is the newest day every required series has. Rows dated after the last requested day are rejected. A day of the generation mix must add up to the system generation. The weather average needs every city. Weather and the ONI are optional datasets, so an outage of NOAA or Open-Meteo does not stop the forecasts; the gate stops them only when the stored data is too old.

**Health reports age.** `status` is `ok`, `stale` or `degraded` with `reasons` and `ages`. `degraded`: a required dataset failed, there is no dataset or model recorded, or production serves the bundled snapshot. An optional dataset (weather, ONI, market, contracts, regional) that fails is reported but does not change the status unless it has been silent for longer than the gate allows. `stale`: the newest day of price or demand is more than 5 days old, the model more than 3 days, or the forecast more than 2. The failure text of a dataset is no longer published, only a reason code. The forecast pages show when the forecast was issued and warn after 2 days. The answer is always HTTP 200 and monitors read the status word.

**Alerts.** The `Watchdog` workflow reads the health endpoint every morning (a second time, ten minutes later, if the first was not `ok`) and opens one issue when it is not `ok`, which GitHub emails; it closes the issue on recovery. A failed `Daily pipeline` run opens a second issue. An external monitor (docs/runbook.md) covers the case in which GitHub stops running workflows.

## Consequences
- A real change of regime (a price that stays above 1.5 times its 90-day maximum, or below half its minimum) is refused by the gate until a person reads the log and dispatches the run with `warn`. That is on purpose for a forecast that people act on; the previous forecast stays visible with its age, and the watchdog opens an issue. Run twice a day, the schedule retries by itself when the data moves back.
- The pipeline fails more visibly (a red run and an issue) where it used to publish quietly.
- The anomaly step, the briefing and the site refresh still run when the gate refuses a forecast, because the ingested data is good.
- Dropped days are not deleted; see ADR 0013. A persistent new level is accepted after 3 held-back days, which supersedes the last consequence of ADR 0013 (a real jump no longer waits a week).

## Rejected alternatives
- Warn only. It is the situation that existed: a bad forecast reached `forecast_log` and could not be removed from the record.
- Publish with a flag. The page would still show the figure.
- A fallback forecast (the naive) when the gate refuses. It adds a second product that nobody has validated, and the site would mix two kinds of forecast.
- A moving z-score per series. With 3 218 days and changing regimes it is fragile; fixed limits wide enough for the observed extremes are easy to explain and to audit.
- Failing hard (HTTP 500) when the site would serve the snapshot in production, or when data is old. It would take the site down for a data problem. The site says what it is showing instead.
- A CAPTCHA on the chat against quota abuse: an external service and personal data, for a site without accounts. Limits by network (IPv6 by /64) and by hour are enough.
