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
