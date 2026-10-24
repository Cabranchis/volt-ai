# ADR 0004: Rolling-origin backtesting

Status: accepted (2026-10-24)

## Context
A single train/test split can flatter a model by landing on an easy period. Electricity demand and price have regime changes (2020 lockdown, El Niño years).

## Decision
Evaluate with a rolling origin: several cutoffs, each trained only on data before the cutoff and scored on the horizon after it. Report MAPE, sMAPE, MASE and the coverage of the P10-P90 interval, per horizon day and overall.

## Consequences
- Training cost is multiplied by the number of cutoffs. The number is capped to stay inside the CI time limit.
- No information from after a cutoff may reach its training set. Features are built per cutoff and a test asserts this.

## Rejected alternatives
- Random k-fold: leaks the future into training for time series.
