# STATE

Working notes for the project: current status, environment and open items.

## Status

| Phase | Description | Status |
| --- | --- | --- |
| 1 | Scaffolding, docs, quality tooling | done |
| 2 | Data: migrations, sources, validation, backfill | done |
| 3 | ML: features, baselines, LightGBM, backtest, SHAP, anomalies | done |
| 4 | Web: pages, charts, i18n, REST API | done |
| 5 | AI: typed tools, chat, daily briefing | done (briefing verified with the template; Gemini polish verified with mocks, live run pending quota) |
| 6 | CI/CD and deployment | done: CI green, Vercel live at https://voltia-xi-five.vercel.app/es; daily pipeline workflow not yet run (needs secrets) |
| 7 | Polish and final review | in progress: runbook, README, deep review, Lighthouse |

## Environment

- Project lives in `D:\Projects\voltia` (C: is nearly full, the workspace on OneDrive is not used for dependencies).
- Python 3.12 through uv. The uv cache and interpreters are in `D:\Jarvis\uv` (`UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR`).
- Node 20.18, npm 10.8.
- No Docker, no Vercel CLI.
- Database: Neon (pooled URL). Owner URL in `pipeline/.env`; the web uses the `voltia_ro` role (`DATABASE_URL_READONLY`).
- Remote: `https://github.com/Cabranchis/volt-ai` (personal account; the academic account is `mcabranchiz`). The repository was renamed from `voltia` on 2026-10-26; GitHub redirects the old URL.
- Name: the brand is **Volt-AI** (it was VoltIA until 2026-10-26). Internal identifiers keep `voltia` on purpose: the Python package and CLI, the `VOLTIA_*` variables, the `voltia_ro` database role, the browser storage keys and the Vercel domain `voltia-xi-five.vercel.app`. Renaming those would break production and the stored secrets.

## Open items for the owner

- Done: Actions secrets `DATABASE_URL` and `GOOGLE_GENERATIVE_AI_API_KEY` are set, `web/.env.vercel` was deleted, secret scanning and push protection are on, and the `Daily pipeline` workflow ran green by hand (run 40150965548).
- Review the Dependabot pull requests: #1, #4, #5, #6 pass CI; #2 (vite 8) and #3 (plugin-react 6) fail CI and need the toolchain upgraded together.
- The Gemini free tier is shared across models and was exhausted by testing; the chat falls back to Flash-Lite and then to the offline analyst.
- Review on or after 2027-02-15: the table `weather_forecast_log` has archived rain forecasts since 2026-10-26 (model `gfs_seamless`, 9 points, 16 days). With about 110 days of history, test them as price features in `pipeline/research/` (same protocol as `docs/model-experiments.md`: development origins, paired bootstrap interval against the production model) and promote them only if the interval excludes zero. Check at the same time how many forecasts the live record (`forecast_log`) has scored.
- The wording of the site avoids the word "liquidado" (XM's settlement process has revisions); the data are described as complete public XM data.
- Done on 2026-10-27: `RATE_LIMIT_SALT`, `NEXT_PUBLIC_REPO_URL` and `NEXT_PUBLIC_SITE_URL` are set in Vercel (Production). `NEXT_PUBLIC_*` values are read at build time, so a change needs a redeploy.
- Run the `Weekly backup` workflow once by hand after the push and check that the artifact `volt-ai-backup` appears.

## Done (negative result): bands that adapt to stress (2026-11-02)

Plan approved by Miguel (`~/.claude/plans/cryptic-kindling-cat.md`). Result recorded in `docs/model-experiments.md` ("Calibration that adapts to stress").

- [x] A1. `pipeline/research/run_calibration.py`: V0 current, V1 recency-weighted, V2 volatility-normalised, V3 by regime, on the saved development rows. V0 reproduces production exactly.
- [x] A2. Decision rule written before running: none of V1-V3 qualified (coverage in the volatile third was already 0.786 with V0; V1/V2 moved it to 0.832, widened the band 5-20 % and lost on pinball, V3 significantly). Stop.
- [x] A3. The reported origins were NOT run (the rule stops at A2). "Reported runs" stays at 8.
- [x] B (calibration change) is cancelled. Nothing in production changes.
- Finding for later, exploratory only: origins with thermal share above 30 % had MASE 3.65 and coverage 0.67 against 0.87 and 0.85 (11 of 50 production origins, two episodes). Volatility and reservoir level did not separate them. Next step if Miguel wants it: a "high thermal share" note on the Price page worded as a past pattern, and track it on live origins before calling it a warning. Other ideas still open: weekly NOAA ENSO series; rainfall forecasts archived from now on (evaluate on/after 2027-02-15); live-record alert when recent coverage drops below 65 %.

Verify with: `cd pipeline/research && uv run --project . python run_calibration.py` (about 1 minute).

## Done: results page "Volt-AI in El Niño" (started 2026-11-02, reframed 2026-11-07)

Goal: a page that shows, with the forecasts made on the day, how the price model behaved in the 2023-24 El Niño, the 2024 supply shock and the El Niño of 2026. Decided with Miguel: "with curves" (re-run the backtest to keep the P10/P50/P90 of each origin).

- [x] `pipeline/research/case_el_nino.py`: re-runs the production price backtest on the local SQLite copy and keeps every row (`research/results/case_el_nino_rows.json`). It reproduced the production MASE per origin exactly (max difference 0.0000).
- [x] `pipeline/research/case_el_nino_pack.py`: writes `web/src/lib/case-study/el-nino.json` (regime scores, four cases with the 21 days before each origin, monthly market context). Regenerate it after a new training run only if the scores should move; the four cases are fixed origins.
- [x] Page `/[lang]/case-study` (ES/EN), chart `CaseChart`, nav item, tests (`el-nino.test.ts`, e2e for both languages, axe light/dark). tsc, eslint, vitest (191) and Playwright (91) pass.
- [x] Independent review by `deep-reviewer`: 18 findings, all applied. Main ones: the MASE definition in the copy was wrong (it is relative to a weekly seasonal naive); "forecasts made on the day" overclaimed (they are walk-forward reconstructions with today's model); the ONI row now uses the value already published at month end (it was hindsight); case texts are keyed by origin; the scripts fail if they do not reproduce production and check the `runId`; numbers in the copy come from the JSON or the live series.
- [ ] Push, then check https://voltia-xi-five.vercel.app/es/case-study (the "latest month" column must read live data, not fixtures).
- [ ] Link the page from LinkedIn text and `docs/comercial/primeros-contactos.md`.

Findings it states (all from stored backtest, price, 14 days, MASE): El Niño 2023-24 origins 2.71 (ETS 3.35, naive 3.59); supply shock Sep-Nov 2024 5.33 (ETS 4.20: the model lost); calm Jan 2025-Jun 2026 0.69; El Niño 2026 so far 0.85 (4 origins). April 2024 (price fell ~90% in two weeks when the drought broke) and October 2024 (ONI −0.2, a supply shock) are the failures. Decision rule: never present the four cases as a sample; the table scores all 50 origins.

Verify with: `cd web && npx tsc --noEmit && npx eslint src && npx vitest run`, `npx next build` then `PW_CHANNEL=msedge npx playwright test`; reproduce the data with `DATABASE_URL=sqlite:///data/voltia.sqlite uv run python research/case_el_nino.py` in `pipeline/`.

Reframed on 2026-11-07 at Miguel's request: the page now shows only what is valuable and attractive for clients (headline figures, error by period, El Niño then and now, four forecasts where Volt-AI beat both references: 2024-01-02, 2025-01-14, 2026-06-23, 2026-09-15). The failure cases (April and October 2024 charts) were removed from the page. The independent review made me keep the full partition of the 50 dates in the table: the row "Supply shock 2024 (May to Dec)" (12 dates) shows Volt-AI level with ETS (MASE 2.61 against 2.55), because hiding it made "lowest error in every period" misleading. Decisions kept for honesty: the cases are labelled as examples chosen among the 31 of 50 dates where the model beat both references; the total row still includes Sep-Nov 2024 and the text says so; forecasts are described as reconstructions; the Models page and `/api/v1/model` still publish the full backtest per origin. Do not remove those disclosures. Nav label: "Results" / "Resultados" (route `/case-study`).
On 2026-11-10 the page was regenerated with 51 test dates (the backtest gained the 2026-10-06 origin, where Volt-AI lost: MASE 1.63 against 1.08 naive and 1.19 ETS). The "El Niño 2026" row now runs from Jul and holds 5 dates (Volt-AI 1.01, ETS 1.07), so the statement "lowest average error in three of four periods" is true but narrow: re-check it whenever the page is regenerated.
The rain-forecast archive (`weather_forecast_log`, migration 0005) already exists and fills daily; evaluate rain features on or after 2027-02-15.

## In progress: update and train as soon as XM publishes a new day (started 2026-10-28)

Goal: reach the newest complete day XM has and retrain right away, instead of waiting for the two fixed runs. Why: on 2026-10-28 XM already had 2026-10-25 complete (24 h of price and generation) while the database and the model stopped at the 24th; XM publishes at no fixed hour and GitHub delays the cron by hours. Plan: `~/.claude/plans/cryptic-kindling-cat.md` (the decisions below are the same).

Decisions: a light hourly workflow `poll.yml` runs `voltia check` and dispatches `pipeline.yml` only when the newest complete XM day is later than the data end of the latest model run (comparing with the model, not with `ingest_log`, so a failed training is retried). `pipeline.yml` stays unchanged. Rejected: a full pipeline every hour (9 min of training x 24 a day), a reusable workflow (shared concurrency group deadlocks), watching only the price (training needs price and demand).

- [x] Step 0: ran `Daily pipeline` by hand on 2026-10-28; the model run `20261028T125447Z-bcaccad` uses data to 2026-10-25 (training took about 9 minutes).
- [x] `voltia check` command (`pipeline/src/voltia/cli.py`) and `db.latest_model_data_end`, with tests in `pipeline/tests/test_check.py` (151 tests pass, 97 % coverage; real XM answered `2026-10-25`).
- [x] `.github/workflows/poll.yml` (hourly at minute 17, `actions: write`, brake after 3 failed pipeline runs).
- [x] Docs: runbook, deployment, architecture, security.
- [x] Monthly health routine prompt updated: it now checks that `poll.yml` is active and had a successful run in the last 6 hours, and flags 3 pipeline runs in a row that did not succeed.
- [x] After the push: `poll.yml` by hand with the model up to date answered `new_data=false` in 29 seconds (XM 2026-10-25, model 2026-10-25) and dropped the unsettled demand of the 26th.
- [x] Seen in production: on 2026-11-02 18:21Z the watcher started the pipeline by itself (event `workflow_dispatch`) and it ended in success.
- Open option: give `voltia check` the read-only database role through a second GitHub secret (the check only reads); today it uses the write URL.

Verify with: `uv run --frozen pytest`, `ruff`, `mypy`; `voltia check` against the local SQLite; on GitHub, the two manual polls.

## In progress: the site shows the new data as soon as the pipeline ends (started 2026-10-31)

Goal: the first visitor after a quiet period must not see old data. Measured on 2026-10-31 04:08 UTC: `/api/v1/health` returned the state of 2026-10-29 09:59 (`X-Vercel-Cache: STALE`, stale-while-revalidate) and the next call returned the real state; `/en/models` showed the track record of the 25th when the 26th was already stored. `getHealth` already uses `cacheLife("minutes")`, so shortening the profile does not fix it. Plan: `~/.claude/plans/cryptic-kindling-cat.md`.

Decisions: tag every cached accessor with `cacheTag("data")`; a protected `POST /api/revalidate` (Bearer `REVALIDATE_TOKEN`, constant-time compare, rate limited) calls `revalidateTag("data", { expire: 0 })`; the last step of `pipeline.yml` calls it (never fails the run). Rejected: a Vercel deploy hook (rebuilds the whole site on every run) and only shortening `cacheLife`.

- [x] Code: `web/src/lib/data/index.ts` (10 accessors tagged), `web/src/app/api/revalidate/route.ts` and its test (185 unit tests, 85 e2e pass), e2e check.
- [x] `pipeline.yml` step "Refresh the site" (warns and continues while the secret is missing).
- [x] Secret `REVALIDATE_TOKEN` in GitHub and in Vercel (sensitive, Production and Preview), set 2026-10-31 without printing the value; site redeployed (endpoint answers 401 without the token, no longer 503).
- [x] Docs: architecture, deployment, runbook, security.
- [x] Verified in production 2026-10-31: manual `Daily pipeline` run 41204499613 succeeded; step "Refresh the site" returned `{"revalidated":true}` (HTTP 200); the first request afterwards to `/api/v1/health` came back `X-Vercel-Cache: REVALIDATED`, `Age: 0`, with `xm_price` to 2026-10-28 updated by that run (13:12 UTC). Not measured: the old behaviour on the same day (a fresh deploy had just reset the cache), so the improvement rests on the header and the data being fresh on the first request. Watch the first request of the next mornings.
- Miguel still has to delete the temporary Vercel token (vercel.com/account/tokens) and `web/.env.vercel`.

Verify with: `npx tsc --noEmit`, `npx eslint src`, `npx vitest run`, `npx next build`, `PW_CHANNEL=msedge npx playwright test`; then the production comparison above.
