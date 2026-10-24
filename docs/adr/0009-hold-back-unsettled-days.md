# ADR 0009: Hold back days that XM has not finished settling

Status: accepted (2026-10-24)

## Context
Recorded responses from the live API on 2026-10-24 showed that the newest days are not final, and that each metric lags differently:

| Metric | Last complete day | Newest value |
| --- | --- | --- |
| `DemaSIN` (daily demand) | 2026-10-21 | 2026-10-22 is a placeholder of 259 840 kWh (a normal day is ~245 000 000 kWh) |
| `Gene`, `PrecBolsNaci` (hourly) | 2026-10-21 | newer days are absent |
| Inflows and reservoir volume | 2026-10-23 | complete |

A placeholder passes a "positive number" check. A partly settled day could even sit inside a plausible range, so range checks alone cannot catch it.

## Decision
- Hourly metrics: a day is stored only if it has all 24 hours.
- Demand: a day is stored only if it reconciles with the total generation of the same day (itself built from 24 hours) within 8 %. Across sampled months from 2018 to 2025 the ratio demand / generation stayed between 0.97 and 1.05.
- Freshness is reported per series, from the newest stored day of each series, not per dataset.
- Each update re-reads the last 7 days so that late revisions overwrite earlier values.

## Consequences
- The newest stored demand day lags the hydrology data by up to three days. The UI shows each KPI with its own date.
- If XM publishes a day that is both settled and inconsistent with generation (for example, exports not counted), it is skipped, and a warning is logged. A run of more than 3 consecutive skipped days fails the batch, which surfaces the problem instead of hiding it.

## Rejected alternatives
- Range checks only: lets a partly settled day through.
- Dropping the newest N days blindly: hides data that is already final (the hydrology series) and does not adapt if XM changes its lag.
