# Runbook

What to check and do when Volt-AI misbehaves. Every command runs from `pipeline/` unless noted, with `DATABASE_URL` set to the owner URL (in `pipeline/.env` locally, a secret in GitHub Actions).

## Quick health check

| Question | How to answer it |
| --- | --- |
| Is the site up and is the data fresh? | Open `/api/v1/health`. `status` is `ok`, `stale` (nothing failed, but the data, the model or the forecast is older than the pipeline leaves it) or `degraded` (a dataset failed, nothing is recorded, or production serves the snapshot); `reasons` says which and `ages` gives the days. The overview page also shows "Data through ..." and when the forecast was issued. |
| Did the daily pipeline run? | GitHub → Actions → *Daily pipeline*. A red run means one step failed; open it, the failing step is named. |
| What is in the database? | `uv run voltia status` prints row counts and, per dataset, `last_day`, `status` and `updated`. |

## Symptoms

### The page shows old data

1. Run `uv run voltia status`. If `last_day` is stale and `status=error`, the source failed (see below). If `last_day` is current, the web is serving a cached build.
2. Pages are prerendered and the API is cached for five minutes (ten more while it refreshes). Redeploy the latest commit in Vercel to refresh the baked pages immediately.
3. XM publishes settled values with a delay and the newest days can be unsettled; the pipeline holds those back on purpose (ADR 0009). A lag of one or two days is normal.

### The pipeline refused to publish a forecast ("publication gate")

A red `Train, backtest and forecast` step whose log has `::error::publication gate: not published: ...` is the gate working (ADR 0014): nothing was stored, so the site keeps the previous forecast and shows its age. The watchdog opens an issue "Pipeline: the daily run failed" with the link. Read the rules it names:

- **`the newest day is N days old`**: a source stopped or was refused. Look at `Ingest what is new` (a failed or held-back dataset), fix that, and the next run publishes by itself.
- **`the model is worse than the weekly seasonal naive`, `only N test dates`, `the 80 % range covers ...`**: the backtest is off. Run `uv run voltia train --origins 5 --step 21` locally against a copy of the data and compare before trusting the model; look for a series that changed (the data guards in ADR 0014 should have stopped it earlier).
- **`the central forecast of <day> (x) is outside a to b`**: the price is far from the last 90 days. Either a data defect (check the last days of `price_mean_cop_kwh` against XM) or a real change of regime, such as a dry season starting. Only a person can tell which.
- A real change of regime is the one case where the refusal is wrong. After reading the numbers, start `Daily pipeline` by hand and choose `gate_mode: warn`: it logs the same problems and publishes. Say why in the commit or the issue.

### The daily pipeline failed

- **`Secret DATABASE_URL is not set`**: add the secret in Settings → Secrets and variables → Actions, then re-run.
- **A source step failed (XM, Open-Meteo, NOAA)**: the clients retry with backoff. If the provider is down, re-run later; the previous data stays and `ingest_log` keeps the old `last_day`. The run is idempotent, so a re-run never duplicates rows.
- **`train` failed or timed out** (45-minute job limit; the run takes about 10 minutes locally with 50 reported backtest origins, and about 10 seconds more for every 21 days of new data, because the origins sit on a fixed calendar and none is dropped. Past about 15 minutes, raise `step_days` in `BacktestConfig` or move the first origin forward in whole steps, and say so in the model card): run it locally against the same database with `uv run voltia train --predict`.
- **SSL connection closed**: Neon closes idle connections; the engine pings and recycles them. If it still happens, re-run.

### The chat answers with a fixed summary or says the model is unavailable

- The Gemini free tier has per-minute and per-day quotas shared across models, and Flash is sometimes overloaded. The app tries Flash, then Flash-Lite, then answers from fixed summaries. Nothing needs fixing; quotas reset.
- If it never uses the model, check `GOOGLE_GENERATIVE_AI_API_KEY` in Vercel (Settings → Environment Variables) and redeploy; variables apply to new deployments only.
- If visitors report being limited: 12 questions per client per 10 minutes (an IPv6 client is counted by its /64 network), `CHAT_HOURLY_LIMIT` (60) per hour and `CHAT_DAILY_LIMIT` (400) per day for the language model; past the hourly or daily limit the chat answers from fixed summaries, and it does the same if the limiter's database cannot be reached.

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

## Watchdog and external monitor

The `Watchdog` workflow reads `/api/v1/health` every day at 13:45 UTC (twice, ten minutes apart) and opens the issue "Platform: the health check is not ok" when the status is not `ok`; it comments on it while the problem lasts and closes it when the status is `ok` again. It also opens "Pipeline: the daily run failed" when a `Daily pipeline` run ends in failure. GitHub emails the issues to the repository owner. It reads a public URL and writes issues; it has no secret.

It does not cover GitHub itself: if scheduled workflows are disabled (no repository activity for 60 days) the watchdog stops too. Set up one outside monitor once:

1. Create a free account at uptimerobot.com.
2. Add a monitor of type **Keyword**, URL `https://<site>/api/v1/health`, keyword `{"status":"ok"` (with the opening brace: every dataset in the list has its own `"status":"ok"`, which would match even when the platform is `stale`), alert when the keyword does **not** exist, interval 5 minutes.
3. Add your email as the alert contact.

The top-level status is the first key of the answer, so that keyword is absent for `stale` and `degraded` too: the monitor also tells you when the data or the forecast is old. An optional dataset (weather, ONI, market, contracts, regional) that fails once does not change the status; only a long silence does.

## The site shows old data or an old forecast

The forecast pages say when the forecast was issued and turn the badge red after 2 days; `/api/v1/health` has the status `stale`. Check, in this order: the `Daily pipeline` runs (a red run, or no run at all in the last day: the scheduled workflows may be disabled, section above); the log of `Ingest what is new` (a source that failed or days that were held back); and the publication gate (section above).

## The site shows old data

The pipeline asks the site to refresh at the end of every run (step `Refresh the site`). If a page still shows a day-old date:

1. Open the last `Daily pipeline` run and read that step. A `::warning::` means the request failed or the secret `REVALIDATE_TOKEN` is missing.
2. To refresh by hand: `curl -X POST -H "Authorization: Bearer <the token>" https://<site>/api/revalidate` (an HTTP 200 with `{"revalidated":true}`). Or redeploy the site in Vercel.
3. To rotate the token, create a new random value, set it in GitHub (secret) and in Vercel (sensitive variable), and redeploy.

## The site shows an impossible reservoir or inflow value

XM sometimes publishes the newest hydrology day before finishing it (2026-11-11 arrived as a reservoir level of 7.6 % when the day before was 79 %; ADR 0013). The ingest now drops such days and logs `ingest.hydrology.implausible_days_dropped`. If one still shows:

1. Start `Daily pipeline` by hand: the update re-reads the last 7 days, so a day XM has finished since replaces the stored value. Compare with XM before assuming it is wrong.
2. If the page keeps the wrong value, read the `Ingest what is new` step for the warning. Dropped days are not deleted: the stored value of a dropped day stays until XM serves a plausible one, so a wrong value written before the guard existed has to be replaced by a pipeline run once XM has finished the day.
3. If the real value is outside the limits in ADR 0013, change `HYDRO_STEP_LIMITS` in `pipeline/src/voltia/ingest.py` and record why. After a real jump the next days are held back for about a week, until the jump day falls at the start of the 7-day re-read window.

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

The CSV files of the export were checked to load back with the same rows and the same JSON text by an automated test on SQLite (`test_the_archive_loads_back_into_an_empty_database_with_the_same_rows`). The `psql` step itself has not been rehearsed against a real database: try it once on an empty Neon branch before the day it is needed. Neon also keeps a history of the database (point-in-time restore, from the branch page of the console) for the days of its retention window; use it first when the loss is recent, and the weekly files when it is older.

After adding a table in a migration, grant `SELECT` on it to `voltia_ro` in the same migration (the default privileges in `0002_roles.pg.sql` only cover tables created by the role that ran that migration). A page that needs a table the web role cannot read shows its empty state instead of failing.

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
