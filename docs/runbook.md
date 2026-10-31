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

## The pipeline did not pick up a new day

1. Open the log of the last `Watch XM for a new day` run (Actions tab, step `Is there a complete XM day the model has not used?`). It prints the newest complete day XM has and the data end of the latest *production* model run. Running `voltia check` locally compares with your local SQLite file, not with production, so it cannot answer this.
2. If XM is ahead and no pipeline started, look at the `Start the pipeline` step: it does not start a run while another one is running or queued, and it stops after three failed pipeline runs in a row (it warns instead). Fix the failure first, then start `Daily pipeline` by hand.
3. To pause the watcher, disable the `Watch XM for a new day` workflow in the Actions tab; the two fixed daily runs keep working.
4. GitHub disables scheduled workflows after 60 days without repository activity; re-enable it with "Enable workflow" in the Actions tab.

## The site shows old data

The pipeline asks the site to refresh at the end of every run (step `Refresh the site`). If a page still shows a day-old date:

1. Open the last `Daily pipeline` run and read that step. A `::warning::` means the request failed or the secret `REVALIDATE_TOKEN` is missing.
2. To refresh by hand: `curl -X POST -H "Authorization: Bearer <the token>" https://<site>/api/revalidate` (an HTTP 200 with `{"revalidated":true}`). Or redeploy the site in Vercel.
3. To rotate the token, create a new random value, set it in GitHub (secret) and in Vercel (sensitive variable), and redeploy.

## Restoring the backup

The `Weekly backup` workflow (Sundays, 07:15 Bogotá; also runnable by hand) uploads the artifact `volt-ai-backup` with `forecast_log`, `weather_forecast_log` and `model_runs` as gzipped CSV and a `manifest.json` with row counts and checksums. Everything else is rebuilt with `voltia backfill`.

1. Download the artifact from the workflow run (Actions, then the run, then Artifacts) and unzip it.
2. Check each file against the `sha256` in `manifest.json`.
3. On an empty database, run `voltia migrate`, then load each file with `psql`, which converts every column to its type on the server and fails on a duplicate key instead of overwriting. `model_runs` goes first, because `forecast_log` points at its run ids. On Windows, `gunzip` each file first and use `FROM '<file>.csv'`:

```bash
for table in model_runs forecast_log weather_forecast_log; do
  psql "$DATABASE_URL" -c "\copy $table FROM PROGRAM 'gunzip -c $table.csv.gz' WITH (FORMAT csv, HEADER)"
done
```

4. Compare `SELECT count(*)` of each table with the `rows` in the manifest.

This procedure has not been rehearsed against a real database yet: try it once on an empty Neon branch before the day it is needed.

## Rotating secrets

- **Neon owner URL**: reset the role password in the Neon console, update `pipeline/.env` and the GitHub secret `DATABASE_URL`.
- **Neon read-only role (`voltia_ro`)**: reset its password the same way, then update `DATABASE_URL_READONLY` in Vercel and redeploy.
- **Gemini key**: create a new key in Google AI Studio, update `GOOGLE_GENERATIVE_AI_API_KEY` in Vercel and in the GitHub secret, redeploy, then delete the old key.

If a secret was ever pasted somewhere public, rotate it first and investigate afterwards.

## Routine

| When | What |
| --- | --- |
| Daily, 11:30 and 22:30 UTC | The `Daily pipeline` workflow ingests, trains, forecasts, detects anomalies and writes the briefing. |
| Every hour, minute 17 | The `Watch XM for a new day` workflow runs `voltia check` and starts `Daily pipeline` only if XM has a complete day (price and demand) later than the data end of the latest model run. Most runs end in seconds with `new_data=false`. |
| Weekly | Review Dependabot pull requests; merge only with green CI. Major upgrades of the web toolchain (vite, plugin-react) must go together. |
| After a schema change | Add a numbered file in `db/migrations`; `voltia migrate` applies it. Never edit an applied migration. |
