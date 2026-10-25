# STATE

Working notes for the turn-based workflow (Claude and Codex share the repo through git commits).

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
- Remote: `https://github.com/Cabranchis/voltia` (personal account; the academic account is `mcabranchiz`).

## Open items for the owner

- Done: Actions secrets `DATABASE_URL` and `GOOGLE_GENERATIVE_AI_API_KEY` are set, `web/.env.vercel` was deleted, secret scanning and push protection are on, and the `Daily pipeline` workflow ran green by hand (run 40150965548).
- Review the Dependabot pull requests: #1, #4, #5, #6 pass CI; #2 (vite 8) and #3 (plugin-react 6) fail CI and need the toolchain upgraded together.
- The Gemini free tier is shared across models and was exhausted by testing; the chat falls back to Flash-Lite and then to the offline analyst.
