# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- A live-record alert: `/api/v1/health` reports `liveRecord` (a `verdict` and the share of forecasts inside P10 to P90 over the 28 days ending on the last settled day, per target; it does not change `status`) and the `Watchdog` workflow opens an issue when it stays under 0.55 (`docs/runbook.md`, "The live record is off target").
- The reference "repeat the last price" in the production backtest of the price (error figures and a paired comparison with its interval, no band) and on the Models and For business pages. The verdicts now say "no se distingue" / "no clear difference" when the interval of the paired MASE difference includes zero, instead of "beats". The publication gate is unchanged.
- A Model Confidence Set over the methods of the dense price backtest (`pipeline/research/mcs.py`): the model is the only method in the set at 1 to 3 days (at 4 to 7 days only at the 10 % level); over the whole horizon and at 8 to 14 days it cannot be told apart from ETS or from repeating the last price. A test of a correlation between days that fades with distance for the cost calculator did not beat the current 0.7, so the calculator is unchanged. The reservoir water balance solved as a differential equation was tested as a price feature and did not pass its rule (MASE -0.040, interval [-0.112, +0.022]); production is unchanged (`docs/model-experiments.md`).
- A publication gate: a forecast that is not finite or ordered, is far from the recent price, is worse than the naive, has a miscalibrated range or starts from stale data is refused and nothing is stored (ADR 0014).
- Step guards on the price, market, contract and generation series, compared with the last stored value; required series per batch; rows after the requested range are rejected; partial generation-mix days are dropped.
- `/api/v1/health` reports `ok`, `stale` or `degraded` with reasons and ages; the forecast pages show when the forecast was issued; the `Watchdog` workflow opens an issue when the status is not `ok` or the pipeline fails.
- "Data unavailable" error screens, an `X-Data-Source` header on every API response and a gitleaks scan of the whole history in CI.
- Hydrology days that XM publishes half finished (a reservoir level of 7.6 % after 79 %) are held back at ingest instead of stored (ADR 0013).
- Results page "Volt-AI in El Niño" (ES/EN): headline figures, error by period, El Niño then and now and four forecasts drawn against what happened, with the regenerating scripts in `pipeline/research/`.
- Repository scaffolding, requirements, architecture and decision records.
- Data layer: SQL migrations, XM / Open-Meteo / NOAA clients with retries, pandera validation, idempotent loading and the `voltia` CLI (`migrate`, `backfill`, `update`, `status`).
- Handling of unsettled newest days reported by XM (ADR 0009).
- Models: LightGBM quantile forecasters with conformal calibration, seasonal-naive and ETS baselines, rolling-origin backtest, SHAP drivers, anomaly detection and the model card.
- Web: bilingual (ES/EN) Next.js app, ECharts dashboards, public REST API v1, security headers, Playwright and axe tests.
- AI analyst: streaming chat with typed tools, rate limits, Gemini Flash with Flash-Lite fallback and an offline mode.
- `voltia brief`: daily ES/EN briefing built from a template and optionally polished by Gemini; the rewrite is discarded if it adds a number that is not in the facts.
- GitHub Actions: CI for both sides and the daily pipeline workflow.

### Changed
- An XM dataset has a time budget of 300 seconds per 31-day window of a normal update, retries included, so one hanging source fails early instead of using up the 45 minutes of the run (a backfill and the first load of a dataset have no limit). The `Watchdog` also reports a daily run that reached that limit, which GitHub calls `cancelled`.
- The API cache is five minutes instead of an hour. Series requests are normalised (sorted, clamped to the history), limited to 8 series and refuse unknown parameters; `health`, `model`, `forecasts` and `openapi` have a per-client limit.
- The chat counts an IPv6 client by its /64, has an hourly cap and answers from fixed summaries when its limiter is down; the request body is read with a byte cap.
- Weather and the ONI no longer stop the pipeline when their source is down; the gate stops forecasts only when their stored data is too old. The anomaly step, the briefing and the site refresh still run when the gate refuses a forecast.
- `/api/v1/health` no longer publishes the text of pipeline errors, only a reason code.
- A hydrology or price level that really changed is held back for 3 days and then accepted (it used to wait about a week).

### Fixed
- Open-Meteo answering 503 or 429 for a minute no longer loses the day's weather: the client waits 2, 4, 8, 16 and 32 seconds over six attempts (it gave up after 15 seconds; on 2026-11-20 that left the weather of the day unloaded until the next run).
- Pooled database connections are pinged and recycled, so Neon closing idle connections no longer breaks long backfills.
- Timestamps are read as UTC, so the web no longer shows them shifted by five hours.
- The chat no longer receives an already-aborted request signal on Vercel, and an empty model stream is reported instead of shown as a blank answer.
