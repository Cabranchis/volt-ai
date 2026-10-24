# ADR 0003: LightGBM quantile regression, always compared with baselines

Status: accepted (2026-10-24)

## Context
We need forecasts with uncertainty for daily demand (30 days) and daily spot price (14 days), using exogenous drivers: weather, reservoir level, inflows, ONI, holidays.

## Decision
Train one LightGBM model per target and quantile (P10, P50, P90) on lag, calendar and exogenous features. Compare each against two baselines: seasonal naive and ETS. Explain predictions with SHAP.

## Consequences
- Fast CPU training that fits in a CI job.
- Intervals come directly from the quantile objective. Coverage is measured, not assumed.
- The model card publishes the real metrics, including cases where the model does not beat a baseline.

## Rejected alternatives
- Prophet: heavier dependencies and weaker with exogenous drivers.
- LSTM or Transformer: more costly to train and explain, with no clear gain on a few thousand daily points.
