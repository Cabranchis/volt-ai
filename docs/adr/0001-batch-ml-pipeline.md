# ADR 0001: Train and predict in a scheduled pipeline, serve stored forecasts

Status: accepted (2026-10-24)

## Context
The web app runs on Vercel. Python functions there are limited in size (about 250 MB unzipped) and start cold. LightGBM, pandas and SHAP together get close to that limit. Forecasts only change once a day, when XM publishes new data.

## Decision
A GitHub Actions workflow runs the Python pipeline daily. It trains, predicts and writes forecasts, explanations and anomalies to PostgreSQL. The web app only reads.

## Consequences
- Page loads are fast and cheap: no model inference per request.
- The pipeline can use heavier libraries without a deployment size limit.
- Forecasts are at most one day old. The UI shows the generation date.

## Rejected alternatives
- Inference in Vercel Python functions: size limit and cold starts.
- A FastAPI service on a free host: it sleeps after inactivity and adds another account to manage.
