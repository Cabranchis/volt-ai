# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Repository scaffolding, requirements, architecture and decision records.
- Data layer: SQL migrations, XM / Open-Meteo / NOAA clients with retries, pandera validation, idempotent loading and the `voltia` CLI (`migrate`, `backfill`, `update`, `status`).
- Handling of unsettled newest days reported by XM (ADR 0009).
- Models: LightGBM quantile forecasters with conformal calibration, seasonal-naive and ETS baselines, rolling-origin backtest, SHAP drivers, anomaly detection and the model card.
- Web: bilingual (ES/EN) Next.js app, ECharts dashboards, public REST API v1, security headers, Playwright and axe tests.
- AI analyst: streaming chat with typed tools, rate limits, Gemini Flash with Flash-Lite fallback and an offline mode.
- `voltia brief`: daily ES/EN briefing built from a template and optionally polished by Gemini; the rewrite is discarded if it adds a number that is not in the facts.
- GitHub Actions: CI for both sides and the daily pipeline workflow.

### Fixed
- Pooled database connections are pinged and recycled, so Neon closing idle connections no longer breaks long backfills.
- Timestamps are read as UTC, so the web no longer shows them shifted by five hours.
- The chat no longer receives an already-aborted request signal on Vercel, and an empty model stream is reported instead of shown as a blank answer.
