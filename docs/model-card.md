# Model card: VoltIA demand and spot-price forecasters

Last training run: `20261026T032630Z-eb8f132`, trained 2026-10-26 03:26 UTC by the scheduled workflow on data from 2018-01-01 to 2026-10-22 (the last day XM had settled for both demand and price). Every number below comes from that run's `model_runs.metrics` row, also saved in [`pipeline/research/results/stored_run_20261026.json`](../pipeline/research/results/stored_run_20261026.json). The previous version of this card described run `20261024T214240Z-280431a`, whose data ended one day earlier. The experiments behind the changes are in [`model-experiments.md`](model-experiments.md).

**This is a portfolio project. The forecasts are not suitable for trading, bidding, hedging or any operational or financial decision.**

## Intended use

- Show, on the VoltIA site, where daily national electricity demand (next 30 days) and the daily mean spot price (next 14 days) are likely to go, with an 80 % interval (P10 to P90) and the main drivers of each forecast.
- Explain the method and its measured accuracy to a technical reader, including where it fails.

Out of scope: hourly or intraday forecasts, regional prices, market bidding, and any use where a wrong forecast has a cost.

## Data

| Input | Source | Notes |
| --- | --- | --- |
| `demand_kwh` (target) | XM `DemaSIN` | kWh/day, 3,215 days; one missing day (2020-06-24) |
| `price_mean_cop_kwh` (target) | XM `PrecBolsNaci` | Mean of the 24 hourly prices, COP/kWh, 65 to 2,499; heavily right-skewed |
| Reservoirs, inflows | XM `PorcVoluUtilDiar`, `PorcApor` | Daily |
| Generation mix | XM `Gene` by resource | Thermal, solar and wind shares |
| Weather | Open-Meteo, mean of Bogotá, Medellín, Cali and Barranquilla | Used only as lags known at the origin |
| ONI | NOAA CPC | Monthly; used only 75 days after the month it is stored on (see Features) |
| Holidays | `holidays` package, Colombia | Known in advance |
| Programmed dispatch cost | XM `CostMargDesp`, mean of the 24 hours | Published the day before it applies; price model only |
| Contract prices | XM `PrecPromCont`, `PrecPromContNoRegu` | About five days late; weeks without a value |
| Scarcity price | XM `PrecEsca` | About three days late |
| Spilling, turbined volume, usable capacity | XM `VertEner`, `VolTurbMasa`, `CapaUtilDiarEner` | Spilling is listed only on days it happened; the rest are daily |

The newest days are held back until XM settles them (ADR 0009), so forecasts start the day after the last settled day of each target.

## Features

Each training row is a pair (origin T, horizon h), and its target is the day T + h. XM settles the price about three days after its day, so a forecast whose origin T is the last settled day is made on day A = T + 3. A feature uses only:

- values observed on or before T,
- for the price model, values of series XM publishes sooner than the settled price, read up to the day each is published by A and never beyond (see "Market state" below),
- calendar facts about the target day, which are known in advance.

The full list, with Spanish and English names, is in [`pipeline/src/voltia/feature_labels.json`](../pipeline/src/voltia/feature_labels.json).

- **Own history**, relative to the level at T:
  - the last value and the previous one, each against the 7-day mean;
  - the same weekday in the last observed week;
  - the mean of the last four same weekdays;
  - the same day last year, against the level at that time;
  - momentum (7 vs 28 days, 28 vs 91 days);
  - year-on-year change;
  - 28-day volatility.
- **Cross-market at T**:
  - for price: demand year-on-year, and hourly price spikes (max over mean) in the last 7 days;
  - for demand: spot price year-on-year.
- **Hydrology and mix at T**:
  - reservoir level, plus its change over 7 days, over 30 days and year-on-year;
  - inflows against the historical mean, averaged over 7, 30 and 90 days;
  - thermal share over 7 days;
  - solar and wind share over 28 days.
- **Weather at T**: 7-day mean temperature, 30-day temperature against last year, and 30-day rainfall. The weather of the target day is **not** used, because it is not known when the forecast is made.
- **ONI**: the latest value already published at T, plus its 3-month change.
  - NOAA publishes the season centred on month M early in M + 2, so a value stored on day 1 of M is used only from that day plus 75 days. On 2026-10-21 the latest usable value is August 2026 (+2.16).
  - This is stricter than the 45 days first proposed, which would have used September before NOAA published it.
- **Market state (price model only)**, relative to the 7-day mean log price at T:
  - the programmed dispatch cost of the days XM has not settled yet. It is read for h = 1 and 2, as the cost of that target day and as its average, with a version corrected by the recent gap between the settled price and the dispatch cost. The cost is programmed the day before, so a one-day margin is kept: it is usable up to A - 1;
  - the average contract price, the unregulated-market contract price and the scarcity price, and the gap between spot and contract prices over 28 days;
  - the newest hydrology: reservoir change since the last settled day, change in inflows, spilled energy over 7 days and against the previous 28, turbined water against the last quarter, and reservoirs against usable capacity.
- **Target-day calendar**:
  - weekday, month and time of year;
  - public holiday and non-working day;
  - long weekend ("puente", a run of three or more non-working days, mostly created by the Emiliani law);
  - Holy Week, the year-end season, and Dec 24, 25, 31 and Jan 1;
  - days to the next holiday and since the last one;
  - whether the reference days (last week, last year) were non-working;
  - the horizon h.

**Leakage guard.**
- `build_features(history, origin, horizons)` truncates the history at the forecast date A = T + 3 before computing anything, and each series is read only up to the day it is published by then (`PUBLICATION_LAG_DAYS` in `features.py`).
- A unit test mutates, for each series, every value from the first day not yet published at A and asserts the feature rows are bit-identical. A second test checks that moving that cut one day earlier does change the features, so the first test can fail.
- A second test asserts that the vectorised table used for training gives exactly the same rows as the truncated build, for several origins and both targets.
- Training rows at a backtest cutoff are restricted to target days on or before the cutoff.

## Method

- **Model**: LightGBM with the quantile objective, one booster per target and quantile (P10, P50, P90), in a direct multi-horizon design. One model per quantile covers every horizon, and h is a feature.
- **Target**: log(y[T + h]) minus a reference known at T. The reference is the last value for the price and the 7-day mean for the demand (both chosen on development origins, see below). Predictions are transformed back with exp, so they are always positive.
- **Crossing**: the three predictions are sorted per row, so p10 ≤ p50 ≤ p90 always holds.
- **Hyperparameters**:
  - 400 rounds, learning rate 0.04, 15 leaves, at least 100 rows per leaf;
  - bagging 0.7, feature fraction 0.8, L2 1.0, 127 bins;
  - seed 20261024, 2 threads, deterministic mode.
- **Interval calibration**: asymmetric conformalised quantile regression (CQR).
  - The lower and upper bounds are shifted separately, in log units, by the ⌈(n+1)(1−α)⌉-th smallest past conformity score, with α = 0.10 per tail. The shift is computed per horizon bucket.
  - In the backtest an origin uses only scores from earlier origins whose outcomes were already observed on that origin's date.
  - Production forecasts use all backtest scores; every outcome among them precedes the training date.
  - P50 is never moved.
- **Explanations**: SHAP TreeExplainer on the P50 booster.
  - Each forecast row stores its top 5 drivers. A driver's contribution in target units is forecast × (1 − e^(−φ)): how much the forecast would change if that feature's term were removed. Drivers explain the deviation from the reference (the last observed value), not the reference itself.
  - When the boosters cross and are re-sorted, the drivers still describe the median booster.

### How the design was chosen (development origins, not reported)

Choices were made on 10 development origins, 60 days apart, from 2021-07-25 to 2023-01-16, scored on uncalibrated output. The latest outcome they use is 2023-02-15, nine months before the first reported origin.

| Target reference | Demand MASE | Demand mean pinball (kWh) | Price MASE | Price mean pinball (COP/kWh) |
| --- | --- | --- | --- | --- |
| 7-day mean (`level7`) | 0.709 | 1.32e6 | 1.279 | 17.4 |
| Seasonal naive (`seasonal_naive`) | 0.766 | 1.37e6 | 1.305 | 18.1 |
| **Last value (`last`, chosen)** | **0.664** | **1.25e6** | **1.232** | **16.5** |
| *Seasonal naive baseline* | 0.977 | 1.91e6 | 1.628 | 21.3 |
| *ETS baseline* | 0.941 | 1.97e6 | 1.323 | 16.4 |

**Disclosure.**
- An earlier development run, before the Dec 24/25/31 and Jan 1 calendar flag existed, favoured the 7-day mean for demand. A full backtest with that setting was run once on the reported origins, with demand MASE 0.707.
- Demand was then switched to `last` because the development table above, recomputed with the final features, favoured it. On the reported origins the switch is slightly worse (0.718), not better.
- Tree size was compared once on the development origins (7 and 31 leaves against 15), and the default was kept. Nothing else was tuned.

### Second round of design work (2026-10)

The price model lost to ETS, so a second round looked for information the first one did not use, and tried other model families on it. The full ledger, generated from the result files, is [`model-experiments.md`](model-experiments.md).

- **Selection** used only development origins: 45 origins every 30 days from 2020-03-01 to 2023-10-12 (37 scored after calibration warm-up), all of whose outcomes precede the first reported origin. 44 price results and 7 demand results were produced, counting baselines, ensembles and failures.
- **What helped.** The programmed dispatch cost, which XM publishes before it settles the price, and the other series in "Market state". On the development origins they cut the price MASE from 1.85 to about 1.50 and the MAPE of the first three days from 11.3 % to 7.5 %. Model family, hyperparameters, recency weights, an ETS-residual hybrid and ensembles of trees all landed within 1.48 to 1.53 of each other, inside the noise of 37 origins; the information, not the algorithm, made the difference.
- **What did not help.** Statistical models from `statsforecast` (AutoETS, AutoARIMA, AutoTheta, MSTL) matched ETS (MASE 1.80 to 1.89). Ridge with residual quantiles reached 1.63, a quantile random forest 1.61, CatBoost 1.53. The Chronos-2 foundation model, zero-shot on the price alone, reached 1.66; with covariates it was worse (1.81), fine-tuned it was much worse (2.26). N-HiTS reached 2.13. Averaging Chronos-2 with the tree models did not improve them.
- **Finalists** were fixed before looking at the reported origins: LightGBM and XGBoost on the same features, and their average. Each ran once on the reported origins (the harness refuses a second run). LightGBM with default parameters was kept because the three were statistically tied and it needs no new dependency.
- **Demand**: the only change that beat the production model on the development origins with a paired interval that excludes zero was the 7-day-mean reference (MASE 0.686 against 0.748, wins at 28 of 37 origins). On the reported origins it is better by a smaller margin (0.706 against 0.722 in the same harness).
- **On the reported origins** the price improvement is smaller than on the development origins, because the reported period holds the 2023-24 El Niño regime and the 2024 spikes, where dispatch cost says little about next week's price. On the research snapshot, with the previous model and the new one run on identical origins (2023-11-21 to 2026-09-21), the price MASE fell from 2.02 to 1.80 (-11 %) and stayed above ETS (1.73); the demand MASE went from 0.722 to 0.706. On the stored run of 2026-10-26, whose origins are one day later, the new price model has MASE 1.48 against 1.54 for ETS, not a significant difference. A one-day shift of the 24 origins moves ETS alone by about 0.2 MASE, so read the price model as level with ETS overall and clearly better over the first week.
- **Probability of a price spike.** A dedicated LightGBM classifier did not beat simpler readings on the reported origins and is not shipped. Reading P(price > threshold) from the forecast's own P10, P50 and P90 as a log-normal beat ETS and persistence for "above 500 COP/kWh" and for "1.3 times the last 30-day mean" in both periods (Brier 0.087 and 0.144 on the reported origins against 0.113 and 0.174 for ETS); above 800 COP/kWh it did not, so that threshold is not offered. The reported-origin figures for this reading were computed after seeing the development result, so they are post hoc.
- **Monthly price outlook.** The mean price of the next three 30-day windows was tried with persistence, a seasonal ratio, ridge, a regularised LightGBM and an analog method. None beat persistence with a paired interval that excludes zero on the development origins, and on the reported origins the errors reached 30 to 85 %. No monthly outlook is published.

## Backtest protocol

- **Origins**: rolling origin with an expanding window, retraining at every origin. 24 reported origins, 45 days apart, from 2023-11-22 to 2026-09-22 in the run above (2023-11-21 to 2026-09-21 in the previous one), so they cover the 2023-24 El Niño price regime and the 2024 price spikes.
  - The last origin leaves 30 observed days after it.
  - 8 earlier origins (2022-11-26 to 2023-10-07) are run only to seed the interval calibration and are excluded from every metric.
- **Baselines**, computed at the same origins:
  - Seasonal naive: same weekday of the last observed week, repeated. Its P10/P90 come from its own h-step log errors over the previous 2 years.
  - ETS(A,Ad,A): weekly seasonality, damped trend, statsmodels `ETSModel`, fitted on the last 3 years before the origin. Price is fitted on the log scale. P10/P90 come from its 80 % prediction interval.
- **Metrics**:
  - MAPE and sMAPE, in percent.
  - MASE, scaled by the in-sample seasonal-naive (m = 7) MAE of the data before each origin.
  - Pinball loss per quantile, in target units.
  - Empirical coverage of P10 to P90 (nominal 80 %), with the share of outcomes below P10 and above P90.
  - A paired comparison per origin: Wilcoxon signed-rank on the per-origin MASE. The 24 origins are 45 days apart, so their errors are close to independent, but the test is indicative only.
- **Runtime**: the full `voltia train` (32 origins × 2 targets × 3 boosters, plus the baselines and the final fit) took 373 s with 2 LightGBM threads on the development machine, against 346 s before the market features. CI runners are slower; the budget is 12 minutes.

## Results (reported origins only)

### Demand, horizons 1 to 30 days (720 forecasts)

| Method | MAPE % | sMAPE % | MASE | Pinball P10 | Pinball P50 | Pinball P90 | P10-P90 coverage | Below P10 | Above P90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **LightGBM + CQR** | 1.78 | 1.78 | 0.725 | 1.06e6 | 2.05e6 | 9.60e5 | 0.82 | 0.11 | 0.07 |
| LightGBM, raw intervals | 1.78 | 1.78 | 0.725 | 1.09e6 | 2.05e6 | 1.08e6 | 0.59 | 0.17 | 0.25 |
| Seasonal naive | 3.69 | 3.75 | 1.498 | 2.00e6 | 4.24e6 | 2.71e6 | 0.76 | 0.08 | 0.16 |
| ETS | 3.32 | 3.34 | 1.340 | 2.28e6 | 3.79e6 | 1.92e6 | 0.89 | 0.04 | 0.06 |

| Horizon | MASE model | MASE seasonal naive | MASE ETS | MAPE model | MAPE seasonal naive | MAPE ETS | Coverage raw | Coverage CQR | Coverage seasonal naive | Coverage ETS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1-7 | 0.709 | 1.208 | 1.129 | 1.76 | 3.03 | 2.85 | 0.58 | 0.82 | 0.76 | 0.83 |
| 8-14 | 0.565 | 1.407 | 1.171 | 1.37 | 3.46 | 2.89 | 0.69 | 0.85 | 0.81 | 0.91 |
| 15-30 | 0.801 | 1.666 | 1.506 | 1.96 | 4.07 | 3.71 | 0.54 | 0.81 | 0.74 | 0.91 |

Pinball loss is in kWh.

Verdicts:

- **The model beats seasonal naive on MASE by 51.6 % (it wins 22 of 24 origins, Wilcoxon p < 0.001, significant) and beats ETS on MASE by 45.9 % (it wins 23 of 24 origins, Wilcoxon p < 0.001, significant).**
  - It has the lowest MASE in every horizon bucket.
  - Per individual horizon it has the lowest MASE at 30 of 30 horizons.
- **Calibration lifts P10-P90 coverage from 0.59 (raw) to 0.82** (nominal 0.80); the tails are 11% below P10 and 7% above P90. The P90 pinball loss goes from 1.08e+06 (raw) to 9.6e+05.
- The weakest origins are 2024-01-06 (MASE 1.36, coverage 0.40), 2026-09-22 (MASE 1.30, coverage 0.43), 2024-05-20 (MASE 1.22, coverage 0.37).
  - Coverage per origin ranges from 0.37 to 1.00.

### Spot price (daily mean), horizons 1 to 14 days (336 forecasts)

| Method | MAPE % | sMAPE % | MASE | Pinball P10 | Pinball P50 | Pinball P90 | P10-P90 coverage | Below P10 | Above P90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **LightGBM + CQR** | 25.74 | 24.06 | 1.477 | 20.9 | 53.5 | 50.7 | 0.89 | 0.06 | 0.05 |
| LightGBM, raw intervals | 25.74 | 24.06 | 1.477 | 19.0 | 53.5 | 32.3 | 0.66 | 0.15 | 0.19 |
| Seasonal naive | 35.76 | 33.76 | 2.039 | 25.3 | 73.9 | 47.8 | 0.79 | 0.08 | 0.14 |
| ETS | 27.42 | 26.95 | 1.543 | 23.1 | 56.1 | 41.8 | 0.82 | 0.07 | 0.11 |

| Horizon | MASE model | MASE seasonal naive | MASE ETS | MAPE model | MAPE seasonal naive | MAPE ETS | Coverage raw | Coverage CQR | Coverage seasonal naive | Coverage ETS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1-3 | 0.904 | 1.916 | 1.053 | 13.62 | 29.91 | 16.58 | 0.74 | 0.83 | 0.78 | 0.78 |
| 4-7 | 1.411 | 1.782 | 1.374 | 24.07 | 31.21 | 25.58 | 0.67 | 0.91 | 0.79 | 0.80 |
| 8-14 | 1.760 | 2.238 | 1.850 | 31.90 | 40.87 | 33.12 | 0.62 | 0.91 | 0.79 | 0.85 |

Pinball loss is in COP/kWh.

Verdicts:

- **The model beats seasonal naive on MASE by 27.5 % (it wins 19 of 24 origins, Wilcoxon p < 0.001, significant) and beats ETS on MASE by 4.3 % (it wins 14 of 24 origins, Wilcoxon p = 0.360, not significant).**
  - It does not have the lowest MASE in the horizon buckets 4-7 days.
  - Per individual horizon it has the lowest MASE at 8 of 14 horizons.
- **Calibration lifts P10-P90 coverage from 0.66 (raw) to 0.89** (nominal 0.80); the tails are 6% below P10 and 5% above P90. The P90 pinball loss goes from 32.3 (raw) to 50.7.
- The weakest origins are 2024-10-02 (MASE 4.96, coverage 1.00), 2026-05-10 (MASE 4.03, coverage 0.14), 2024-11-16 (MASE 3.68, coverage 0.93).
  - Coverage per origin ranges from 0.14 to 1.00.

### Change against the previous run

The previous run's figures are those published in the earlier version of this card; its 24 origins ended one day earlier, so the two sets are not identical, and a one-day shift moves the price MASE of ETS alone by about 0.2. On identical origins the research harness measured 2.02 to 1.80 for the price and 0.722 to 0.706 for the demand. Buckets are 1-7, 8-14 and 15-30 days for demand and 1-3, 4-7 and 8-14 days for price.

| Target | | MAPE % | MASE | P10-P90 coverage | MASE by horizon bucket |
| --- | --- | --- | --- | --- | --- |
| Demand | previous run | 1.76 | 0.718 | 0.83 | 0.680 / 0.643 / 0.768 |
| Demand | this run | 1.78 | 0.725 | 0.82 | 0.709 / 0.565 / 0.801 |
| Spot price | previous run | 34.75 | 2.021 | 0.87 | 1.270 / 1.917 / 2.403 |
| Spot price | this run | 25.74 | 1.477 | 0.89 | 0.904 / 1.411 / 1.760 |

## Anomaly detection (FR-09)

**Method.**
1. Robust STL on log values: weekly period, 13-week trend window.
2. Huber regression of the residual on holiday flags (weekday holidays, long-weekend Saturdays and Sundays, Holy Week, the year-end season, and Dec 24, 25, 31 and Jan 1), so ordinary holidays are not reported.
3. Robust z-score (median and MAD).
4. Isolation Forest on [z, centred 7-day mean of z, day-to-day change of z].
5. Severity = mean of |z| and the robust z of the forest score.

**Threshold.** A day is flagged when its severity is in the top 2 % and its own |z| is at least 3.5. On pure noise the second condition keeps the flag count well under 1 % (tested).

**Run on 2026-10-24.**
- Demand: 63 of 3,215 days flagged (2.0 %).
- Price: 65 of 3,216 days flagged (2.0 %).

Known events, checked without any date hard-coded:

- **2020 lockdown (demand): flagged, but only the onset.** 16 low days between 2020-03-24 and 2020-04-21 are flagged, with deviations from −6 % to −14 %.
  - May and June 2020 are not flagged: by then the 13-week trend has absorbed the lower level.
  - Six "high" flags between 2020-03-06 and 2020-03-16 are artefacts of the break. The centred trend is pulled down by the drop that follows, so ordinary pre-lockdown days look high.
- **2024 price spikes: flagged.**
  - The April 2024 spike (850 to 1,080 COP/kWh, up to +232 % against the expected level) is flagged, followed by the collapse in late April and May (low flags).
  - The September to November 2024 spikes (2,260 to 2,500 COP/kWh, the series maximum) are flagged high.
- **The long 2023-24 El Niño high-price plateau is not flagged as such.** It lasted months, so it is part of the trend. Flags in that period are sharp drops, mostly around holidays.
- **Other flags with a plausible cause, unverified**: the May 2021 national strike (demand), and year-end price collapses such as 2023-12-30 (−81 %) and 2024-12-31 (−78 %).

## Failure modes and limits

- **Regime shifts**: El Niño droughts, reservoir emergencies, regulatory changes and the 2020 lockdown move price or demand to levels the recent history does not contain. Tree models do not extrapolate; the log-ratio target helps but cannot predict the shift. Intervals are calibrated on average, not per regime: coverage per origin ranges from 0.27 to 1.00 for demand and from 0.07 to 1.00 for price.
- **Price spikes**: the daily mean price can triple within days. Errors on a few spike origins dominate the price metrics.
- **The dispatch cost is a nowcast, not a forecast**: it helps for the two or three days XM has not settled and fades after about a week. It is also an assumption about XM's publication time: it is read only up to the day before the forecast date, and the live record of forecasts versus outcomes, once it exists, is the check.
- **No future weather or hydrology**: the forecasts do not use weather or inflow forecasts, only what is known at the origin. Rain or heat that is not yet visible in the lags is invisible to the model.
- **Holidays the package does not know**, such as ad hoc civic days, are treated as normal days.
- **ONI revisions**: stored ONI values are the latest NOAA revision, not the value first published. The backtest therefore sees slightly better ONI data than was available in real time, a small optimistic bias in the ONI features.
- **Explanations are local and approximate**: SHAP describes the P50 booster, contributions in kWh or COP do not add up exactly to the forecast, and feature correlations (reservoir and inflows, for example) spread credit between related features.
- **Small sample for the paired tests**: 24 origins. The demand result is robust; the price comparisons are not conclusive either way.

## What the model cannot do

It cannot forecast hourly prices, regional prices, or anything beyond 30 days for demand or 14 days for price; a monthly price outlook was tested and is not reliable enough to publish. It cannot anticipate policy decisions, outages or rationing, and it gives no trading signal.

## Reproducibility

- `voltia train --predict` runs the backtest, fits the final models, stores them under `pipeline/models_store/<run_id>/` (LightGBM text files and a JSON manifest, no pickle) and writes the run, the forecasts and their drivers.
- `voltia predict` reforecasts from the latest settled day without retraining. `voltia anomalies` rebuilds the anomaly table.
- The randomness is fixed: LightGBM uses a seed, deterministic mode and a fixed thread count; Isolation Forest uses `random_state`. A test asserts that two training runs on the same data give identical metrics.
- Determinism was also checked on the real data: a second full run on a copy of the database reproduced the stored metrics exactly. A different LightGBM thread count can change the last digits.
