# ADR 0012: Read the series XM publishes before it settles the price

Status: accepted (2026-10-26)

## Context
XM settles the spot price about three days after the day it belongs to (ADR 0009). A forecast whose origin T is the last settled day is therefore made on day A = T + 3, and its first two or three horizons are days that already happened but are not priced yet. Other series arrive sooner. Measured on 2026-10-25:

| Series | Newest day published |
| --- | --- |
| `PrecBolsNaci`, `MaxPrecOferNal`, `PrecEsca` | 2026-10-22 |
| `PrecPromCont`, `PrecPromContNoRegu` | 2026-10-20 |
| Reservoirs, inflows, spilling, turbined volume | 2026-10-24 |
| `CostMargDesp` (marginal cost of the programmed dispatch) | 2026-10-25 |

The programmed dispatch cost tracks the settled price closely (correlation of logs 0.97, MAPE 15 % on the same day, 0.68 correlation of daily changes), and the first version of the price model did not use it.

## Decision
- A feature row for origin T may read a series up to day A minus that series' publication lag, and nothing later. The lags are in `PUBLICATION_LAG_DAYS` (`pipeline/src/voltia/features.py`); a series not listed is read only up to T. The programmed dispatch cost has a one-day margin although it is published the day before: we cannot see from the data whether the stored value was revised intraday.
- `build_features` truncates the history at A and the vectorised training table applies the same shifts. Tests scramble every value after the allowed day, one series at a time, and require identical rows; a second test checks that reading one day too early would change them.
- The price model reads the market state past T (dispatch cost, contract and scarcity prices, newest hydrology). The demand model does not.
- The new series are ingested as two datasets, `xm_market` and `xm_contracts`, so that contract prices, which have gaps of weeks, do not relax the gap check on the others. Both are in `OPTIONAL_DATASETS`: a failure in either is reported as a warning and does not fail `voltia update`, so the daily forecast still runs with those features missing, which the trees treat as unknown. Spilling is stored as 0 on settled days XM lists none for, but the newest turbined day stays empty unless XM listed it, because its spilling may not be published yet.
- The training history is no longer cut at the last settled day; the origins and the training rows still are.

## Consequences
- The backtest, the production forecast and the training table agree on what is known when, so the measured accuracy is what a forecast made on day A would have achieved.
- Day-ahead dispatch information helps only the first few days. Beyond about a week the price model is no better than ETS on the reported origins (see the model card).
- If XM changes when it publishes a series, the lags must change, and a stale lag silently drops information or, worse, reads unpublished values. The live record of forecasts and outcomes is the check.

## Rejected alternatives
- Using the newest value of every series regardless of its publication time: leaks the future in the backtest.
- Moving the origin to A and treating the unsettled days as missing targets: the model would never see the dispatch cost of those days as a target-day feature.
- Folding the contract prices into the main dataset: a 34-day hole would either fail the batch or force a looser check on every series.
