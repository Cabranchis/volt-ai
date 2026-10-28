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

## In progress: update and train as soon as XM publishes a new day (started 2026-10-28)

Goal: reach the newest complete day XM has and retrain right away, instead of waiting for the two fixed runs. Why: on 2026-10-28 XM already had 2026-10-25 complete (24 h of price and generation) while the database and the model stopped at the 24th; XM publishes at no fixed hour and GitHub delays the cron by hours. Plan: `~/.claude/plans/cryptic-kindling-cat.md` (the decisions below are the same).

Decisions: a light hourly workflow `poll.yml` runs `voltia check` and dispatches `pipeline.yml` only when the newest complete XM day is later than the data end of the latest model run (comparing with the model, not with `ingest_log`, so a failed training is retried). `pipeline.yml` stays unchanged. Rejected: a full pipeline every hour (9 min of training x 24 a day), a reusable workflow (shared concurrency group deadlocks), watching only the price (training needs price and demand).

- [x] Step 0: ran `Daily pipeline` by hand on 2026-10-28; the model run `20261028T125447Z-bcaccad` uses data to 2026-10-25 (training took about 9 minutes).
- [x] `voltia check` command (`pipeline/src/voltia/cli.py`) and `db.latest_model_data_end`, with tests in `pipeline/tests/test_check.py` (151 tests pass, 97 % coverage; real XM answered `2026-10-25`).
- [x] `.github/workflows/poll.yml` (hourly at minute 17, `actions: write`, brake after 3 failed pipeline runs).
- [x] Docs: runbook, deployment, architecture, security.
- [x] Monthly health routine prompt updated: it now checks that `poll.yml` is active and had a successful run in the last 6 hours, and flags 3 pipeline runs in a row that did not succeed.
- [x] After the push: `poll.yml` by hand with the model up to date answered `new_data=false` in 29 seconds (XM 2026-10-25, model 2026-10-25) and dropped the unsettled demand of the 26th.
- [ ] Still to see in production: the first time the watcher starts the pipeline by itself, when XM publishes 2026-10-26 (expected within hours; check the `Daily pipeline` runs with event `workflow_dispatch` and the hourly `Watch XM for a new day` log). Unit tests cover that branch; production has not exercised it yet.
- Open option: give `voltia check` the read-only database role through a second GitHub secret (the check only reads); today it uses the write URL.

Verify with: `uv run --frozen pytest`, `ruff`, `mypy`; `voltia check` against the local SQLite; on GitHub, the two manual polls.
