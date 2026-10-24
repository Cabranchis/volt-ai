# ADR 0005: Daily granularity for history, hourly only for the recent past

Status: accepted (2026-10-24)

## Context
The free database tiers are small. XM publishes hourly series, and generation by resource multiplies rows.

## Decision
Store daily aggregates from 2018-01-01. Store hourly system demand and price only for the last 90 days, for the intraday profile chart. Store generation daily by source type, not by individual plant.

## Consequences
- The database stays well under 0.5 GB.
- Models use daily targets. Intraday forecasting is out of scope.
- 2018 onward covers the 2020 lockdown and both El Niño periods.

## Rejected alternatives
- Full hourly history by resource: tens of millions of rows.
