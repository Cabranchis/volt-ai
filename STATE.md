# STATE

Working notes for the turn-based workflow (Claude and Codex share the repo through git commits).

## Status

| Phase | Description | Status |
| --- | --- | --- |
| 1 | Scaffolding, docs, quality tooling | done |
| 2 | Data: migrations, sources, validation, backfill | pending |
| 3 | ML: features, baselines, LightGBM, backtest, SHAP, anomalies | pending |
| 4 | Web: pages, charts, i18n, REST API | pending |
| 5 | AI: typed tools, chat, daily briefing | pending |
| 6 | CI/CD and deployment | pending |
| 7 | Polish and final review | pending |

## Environment

- Project lives in `D:\Projects\voltia` (C: is nearly full, the workspace on OneDrive is not used for dependencies).
- Python 3.12 through uv. The uv cache and interpreters are in `D:\Jarvis\uv` (`UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR`).
- Node 20.18, npm 10.8.
- No Docker, no Vercel CLI.

## Open items for the owner

- Create the Vercel account (sign in with GitHub).
- Create the PostgreSQL database (Neon or Supabase) and give the two connection strings.
- Optional: Google AI Studio key for Gemini.
- Decide when to create the GitHub repository and push. Nothing is pushed without an explicit request.
