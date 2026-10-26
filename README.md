# VoltIA

**Energy intelligence for Colombia.** VoltIA ingests the public data of the national power market (XM), forecasts electricity demand and spot price with uncertainty bands, detects anomalies, explains what drives each forecast and offers an AI analyst that answers questions using real data.

**Live demo: <https://voltia-xi-five.vercel.app/en>** · [Español](README.es.md) · [Requirements](docs/requirements.md) · [Architecture](docs/architecture.md) · [Model card](docs/model-card.md) · [Decisions](docs/adr) · [Runbook](docs/runbook.md)

![Overview page](docs/img/overview.png)

## What it does

- **Forecasts** daily demand 30 days ahead and spot price 14 days ahead, with calibrated P10/P50/P90 bands.
- **Backtests honestly** with rolling-origin evaluation against seasonal-naive and ETS baselines, and publishes the results even when they are modest.
- **Explains** each forecast with SHAP drivers in plain language.
- **Watches hydrology and El Niño**: reservoir level, inflows and the ONI index, which is at +2.2 in 2026.
- **Detects anomalies** such as the 2020 lockdown and the El Niño years.
- **Answers questions** through an AI analyst limited to typed, validated tools. It never runs free-form SQL, and it still answers from fixed summaries when the model is unavailable.
- **Writes a daily briefing** in both languages from the day's figures.
- **Exposes a REST API** under `/api/v1` with an OpenAPI specification.
- **Works in Spanish and English**, in light and dark themes.

![Demand forecast, dark theme](docs/img/demand-dark.png)

## Results, as measured

Rolling-origin backtest, 50 origins on a fixed calendar (21 days apart), 80 % intervals (full tables and method in the [model card](docs/model-card.md)):

| Target | Against seasonal naive | Against ETS | P10–P90 coverage (nominal 80 %) |
| --- | --- | --- | --- |
| Demand, 30 days | MASE 42.3 % lower, wins 46 of 50 origins | MASE 42.7 % lower, wins 45 of 50 | 0.82 |
| Spot price, 14 days | MASE 33.3 % lower, wins 42 of 50 | 14.2 % lower, but the interval of the difference includes zero; clearly better only in the first days | 0.81 |

Against a plain exponential-smoothing forecast the price model wins in the first days and is level with it beyond a week. The site says so, and presents the price forecast as a calibrated range rather than a better median.

## Stack

| Layer | Technology |
| --- | --- |
| Pipeline | Python 3.12, uv, pandas, pandera, LightGBM, statsmodels, SHAP, SQLAlchemy |
| Database | PostgreSQL on Neon (free tier); read-only role for the web |
| Web | Next.js 16, TypeScript, Tailwind CSS 4, Apache ECharts |
| AI | Gemini Flash with Flash-Lite fallback through the Vercel AI SDK (optional) |
| Delivery | GitHub Actions (CI and the daily pipeline) and Vercel |

Everything runs on free tiers.

## Quality

- Pipeline: ruff, mypy and 109 tests at 96 % coverage, no network in CI.
- Web: eslint, tsc, vitest, a production build and 62 Playwright checks with axe accessibility scans in both themes.
- Security: strict CSP and security headers, a database role that cannot write (except the rate-limit table), an Origin check, body-size cap and per-client limits on the chat, no secrets in the repository.
- Reproducible: lockfiles for both sides and actions pinned by commit.

## Run it locally

```bash
# pipeline (SQLite is used when DATABASE_URL is unset)
cd pipeline && uv sync
uv run voltia backfill && uv run voltia train --predict && uv run voltia anomalies && uv run voltia brief

# web (fixtures when no database is configured)
cd web && npm ci && npm run dev
```

Deployment, secrets and the daily schedule are in [docs/deployment.md](docs/deployment.md); what to do when something breaks is in [docs/runbook.md](docs/runbook.md).

## Repository layout

```
pipeline/   Python package: sources, validation, features, models, briefing, CLI
web/        Next.js application and REST API
db/         Versioned SQL migrations
docs/       Requirements, architecture, ADRs, model card, deployment guide, runbook
```

## Data sources

XM public API, Open-Meteo, NOAA Climate Prediction Center (ONI) and Colombian public holidays. Details and terms are in [docs/requirements.md](docs/requirements.md#6-data-sources-and-terms).

## License

MIT. See [LICENSE](LICENSE).
