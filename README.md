# VoltIA

**Energy intelligence for Colombia.** VoltIA ingests the public data of the national power market (XM), forecasts electricity demand and spot price with uncertainty bands, detects anomalies, explains what drives each forecast and offers an AI analyst that answers questions using real data.

[Español](README.es.md) · [Requirements](docs/requirements.md) · [Architecture](docs/architecture.md) · [Decisions](docs/adr)

> **Status:** under development. Phase 1 of 7 (scaffolding and design). This README is completed with screenshots, metrics and the live demo link in the final phase.

## What it does

- **Forecasts** daily demand 30 days ahead and spot price 14 days ahead, with P10/P50/P90 bands.
- **Backtests honestly** with rolling-origin evaluation against seasonal-naive and ETS baselines, and publishes the results even when they are modest.
- **Explains** each forecast with SHAP drivers in plain language.
- **Watches hydrology and El Niño**: reservoir level, inflows and the ONI index, which is at +2.2 in 2026.
- **Detects anomalies** such as the 2020 lockdown and the El Niño years.
- **Answers questions** through an AI analyst limited to typed, validated tools. It never runs free-form SQL.
- **Exposes a REST API** with an OpenAPI specification.
- **Works in Spanish and English.**

## Stack

| Layer | Technology |
| --- | --- |
| Pipeline | Python 3.12, uv, pandas, pandera, LightGBM, statsmodels, SHAP, SQLAlchemy |
| Database | PostgreSQL (Neon or Supabase free tier) |
| Web | Next.js, TypeScript, Tailwind CSS, Apache ECharts, next-intl |
| AI | Gemini Flash through the Vercel AI SDK (optional) |
| Delivery | GitHub Actions (daily pipeline, CI) and Vercel |

Everything runs on free tiers.

## Repository layout

```
pipeline/   Python package: sources, validation, features, models, CLI
web/        Next.js application and REST API
db/         Versioned SQL migrations
docs/       Requirements, architecture, ADRs, model card, deployment guide
```

## Data sources

XM public API, Open-Meteo, NOAA Climate Prediction Center (ONI) and Colombian public holidays. Details and terms are in [docs/requirements.md](docs/requirements.md#6-data-sources-and-terms).

## License

MIT. See [LICENSE](LICENSE).
