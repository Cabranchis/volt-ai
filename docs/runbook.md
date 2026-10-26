# Runbook

What to check and do when Volt-AI misbehaves. Every command runs from `pipeline/` unless noted, with `DATABASE_URL` set to the owner URL (in `pipeline/.env` locally, a secret in GitHub Actions).

## Quick health check

| Question | How to answer it |
| --- | --- |
| Is the site up and is the data fresh? | Open `/api/v1/health`. It reports the last day of each dataset and the age of the latest model run. The overview page also shows "Data through ...". |
| Did the daily pipeline run? | GitHub → Actions → *Daily pipeline*. A red run means one step failed; open it, the failing step is named. |
| What is in the database? | `uv run voltia status` prints row counts and, per dataset, `last_day`, `status` and `updated`. |

## Symptoms

### The page shows old data

1. Run `uv run voltia status`. If `last_day` is stale and `status=error`, the source failed (see below). If `last_day` is current, the web is serving a cached build.
2. Pages are prerendered and the API is cached for one hour. Redeploy the latest commit in Vercel to refresh the baked pages immediately.
3. XM publishes settled values with a delay and the newest days can be unsettled; the pipeline holds those back on purpose (ADR 0009). A lag of one or two days is normal.

### The daily pipeline failed

- **`Secret DATABASE_URL is not set`**: add the secret in Settings → Secrets and variables → Actions, then re-run.
- **A source step failed (XM, Open-Meteo, NOAA)**: the clients retry with backoff. If the provider is down, re-run later; the previous data stays and `ingest_log` keeps the old `last_day`. The run is idempotent, so a re-run never duplicates rows.
- **`train` failed or timed out** (45-minute job limit; the run takes about 10 minutes locally with 50 reported backtest origins, and about 10 seconds more for every 21 days of new data, because the origins sit on a fixed calendar and none is dropped. Past about 15 minutes, raise `step_days` in `BacktestConfig` or move the first origin forward in whole steps, and say so in the model card): run it locally against the same database with `uv run voltia train --predict`.
- **SSL connection closed**: Neon closes idle connections; the engine pings and recycles them. If it still happens, re-run.

### The chat answers with a fixed summary or says the model is unavailable

- The Gemini free tier has per-minute and per-day quotas shared across models, and Flash is sometimes overloaded. The app tries Flash, then Flash-Lite, then answers from fixed summaries. Nothing needs fixing; quotas reset.
- If it never uses the model, check `GOOGLE_GENERATIVE_AI_API_KEY` in Vercel (Settings → Environment Variables) and redeploy; variables apply to new deployments only.
- If visitors report being limited: 12 questions per client per 10 minutes and `CHAT_DAILY_LIMIT` (400) per day.

### The briefing is missing or looks wrong

`uv run voltia brief` rebuilds today's ES and EN rows in `briefings` (idempotent). Without `GOOGLE_GENERATIVE_AI_API_KEY` it writes the template; with it, Gemini may rewrite the template, and the rewrite is discarded if it adds a number that is not in the facts. The `source` column says which one was stored.

### The forecasts look wrong

- Check `/models` on the site and the [model card](model-card.md): the price median is not better than ETS, and intervals are calibrated on average, not per regime.
- Retrain: `uv run voltia train --predict`. The run is deterministic for the same data. Forecasts of the 10 most recent runs are kept; `forecast_log` keeps every forecast as first issued, for the live track record.
- Regime shifts (a new El Niño phase, reservoir emergencies) are the known weak spot.

## Rotating secrets

- **Neon owner URL**: reset the role password in the Neon console, update `pipeline/.env` and the GitHub secret `DATABASE_URL`.
- **Neon read-only role (`voltia_ro`)**: reset its password the same way, then update `DATABASE_URL_READONLY` in Vercel and redeploy.
- **Gemini key**: create a new key in Google AI Studio, update `GOOGLE_GENERATIVE_AI_API_KEY` in Vercel and in the GitHub secret, redeploy, then delete the old key.

If a secret was ever pasted somewhere public, rotate it first and investigate afterwards.

## Routine

| When | What |
| --- | --- |
| Daily, 11:30 UTC | The `Daily pipeline` workflow ingests, trains, forecasts, detects anomalies and writes the briefing. |
| Weekly | Review Dependabot pull requests; merge only with green CI. Major upgrades of the web toolchain (vite, plugin-react) must go together. |
| After a schema change | Add a numbered file in `db/migrations`; `voltia migrate` applies it. Never edit an applied migration. |
