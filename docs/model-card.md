# Model card: VoltIA demand and spot-price forecasters

Last training run: `20261024T214240Z-280431a`, trained 2026-10-24 21:42 UTC on data from 2018-01-01 to 2026-10-21 (the last day XM had settled for both demand and price). Every number below comes from that run's `model_runs.metrics` row. Re-running `voltia train` on the same data reproduces them exactly (see "Reproducibility").

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

The newest days are held back until XM settles them (ADR 0009), so forecasts start the day after the last settled day of each target.

## Features

Each training row is a pair (origin T, horizon h), and its target is the day T + h. A feature uses only:

- values observed on or before T,
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
- **Target-day calendar**:
  - weekday, month and time of year;
  - public holiday and non-working day;
  - long weekend ("puente", a run of three or more non-working days, mostly created by the Emiliani law);
  - Holy Week, the year-end season, and Dec 24, 25, 31 and Jan 1;
  - days to the next holiday and since the last one;
  - whether the reference days (last week, last year) were non-working;
  - the horizon h.

**Leakage guard.**
- `build_features(history, origin, horizons)` truncates the history at the origin before computing anything.
- A unit test mutates every value after the origin and asserts the feature rows are bit-identical.
- A second test asserts that the vectorised table used for training gives exactly the same rows as the truncated build, for several origins and both targets.
- Training rows at a backtest cutoff are restricted to target days on or before the cutoff.

## Method

- **Model**: LightGBM with the quantile objective, one booster per target and quantile (P10, P50, P90), in a direct multi-horizon design. One model per quantile covers every horizon, and h is a feature.
- **Target**: log(y[T + h]) − log(y[T]). This "last value" reference was chosen on development origins (see below). Predictions are transformed back with exp, so they are always positive.
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

## Backtest protocol

- **Origins**: rolling origin with an expanding window, retraining at every origin. 24 reported origins, 45 days apart, from 2023-11-21 to 2026-09-21, so they cover the 2023-24 El Niño price regime and the 2024 price spikes.
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
- **Runtime**: the full `voltia train` (32 origins × 2 targets × 3 boosters, plus the baselines and the final fit) took 346 s with 2 LightGBM threads on the development machine. CI runners are slower; the budget is 12 minutes.

## Results (reported origins only)

### Demand, horizons 1 to 30 days (720 forecasts)

| Method | MAPE % | sMAPE % | MASE | Pinball P10 | Pinball P50 | Pinball P90 | P10–P90 coverage | Below P10 | Above P90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **LightGBM + CQR** | **1.76** | **1.76** | **0.718** | 1.07e6 | **2.03e6** | **0.86e6** | **0.83** | 0.09 | 0.08 |
| LightGBM, raw intervals | 1.76 | 1.76 | 0.718 | **1.06e6** | 2.03e6 | 0.92e6 | 0.65 | 0.16 | 0.20 |
| Seasonal naive | 3.83 | 3.91 | 1.560 | 2.03e6 | 4.41e6 | 2.83e6 | 0.75 | 0.07 | 0.17 |
| ETS | 3.52 | 3.54 | 1.423 | 2.30e6 | 4.03e6 | 2.04e6 | 0.88 | 0.04 | 0.08 |

| Horizon | MASE model | MASE seasonal naive | MASE ETS | MAPE model | MAPE seasonal naive | MAPE ETS | Coverage raw | Coverage CQR | Coverage seasonal naive | Coverage ETS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1–7 | 0.680 | 1.266 | 1.233 | 1.68 | 3.16 | 3.11 | 0.66 | 0.86 | 0.75 | 0.80 |
| 8–14 | 0.643 | 1.501 | 1.240 | 1.57 | 3.69 | 3.06 | 0.71 | 0.86 | 0.79 | 0.90 |
| 15–30 | 0.768 | 1.715 | 1.585 | 1.88 | 4.19 | 3.90 | 0.61 | 0.80 | 0.73 | 0.90 |

Verdicts:

- **The model beats seasonal naive on demand MASE by 54.0 % and ETS by 49.5 %.** It wins 21 of 24 origins against each, with Wilcoxon p < 0.001 in both cases. It wins in every horizon bucket and at every individual horizon from 1 to 30.
- **Calibration lifts P10–P90 coverage from 0.65 (raw) to 0.83 (nominal 0.80).** The tails come out at 9 % below P10 and 8 % above P90. The calibrated P90 pinball loss is better than the raw one; the P10 loss is about 1 % worse.
- The weak origins are 2024-05-19 (MASE 1.57, coverage 0.27), 2026-09-21 (1.19, 0.47) and 2026-02-08 (0.98, 0.53). On those origins demand moved away from its recent level for weeks at a time. Coverage per origin is therefore much less even than the 0.83 average suggests.

### Spot price (daily mean), horizons 1 to 14 days (336 forecasts)

| Method | MAPE % | sMAPE % | MASE | Pinball P10 | Pinball P50 | Pinball P90 | P10–P90 coverage | Below P10 | Above P90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LightGBM + CQR | 34.75 | 32.80 | 2.021 | 26.0 | 73.2 | 57.3 | 0.87 | 0.07 | 0.07 |
| LightGBM, raw intervals | 34.75 | 32.80 | 2.021 | 28.7 | 73.2 | **44.1** | 0.55 | 0.19 | 0.25 |
| Seasonal naive | 37.09 | 34.66 | 2.131 | 26.4 | 76.9 | 49.5 | 0.77 | 0.08 | 0.15 |
| **ETS** | **31.05** | **30.16** | **1.729** | **25.5** | **62.5** | 47.4 | 0.78 | 0.10 | 0.12 |

| Horizon | MASE model | MASE seasonal naive | MASE ETS | MAPE model | MAPE seasonal naive | MAPE ETS | Coverage raw | Coverage CQR | Coverage seasonal naive | Coverage ETS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1–3 | 1.270 | 1.935 | 1.206 | 21.6 | 32.9 | 21.7 | 0.61 | 0.82 | 0.78 | 0.74 |
| 4–7 | 1.917 | 1.869 | 1.657 | 31.8 | 31.4 | 28.6 | 0.59 | 0.89 | 0.77 | 0.77 |
| 8–14 | 2.403 | 2.365 | 1.995 | 42.1 | 42.2 | 36.5 | 0.51 | 0.88 | 0.77 | 0.80 |

Pinball loss is in COP/kWh.

Verdicts:

- **The price model does not beat ETS.** ETS has a 16.9 % lower MASE overall, and the model wins only 8 of 24 origins (Wilcoxon p = 0.11).
  - ETS is better in every horizon bucket. The model edges it only at h = 2 (MASE 1.31 against 1.35).
  - ETS is also better on P10, P50 and P90 pinball loss.
- **Against seasonal naive the model is 5.2 % better on MASE overall, which is not significant** (14 of 24 origins, p = 0.51).
  - The gain is concentrated in days 1 to 3 (1.27 against 1.94).
  - In the 4–7 and 8–14 day buckets it is slightly worse than seasonal naive. Per horizon it is better at h = 1 to 4, 6, 8 and 9 and worse at the others.
- **Calibration lifts P10–P90 coverage from 0.55 to 0.87, which over-covers (nominal 0.80).** The scores that set the interval width include the 2023-24 El Niño and the 2024 spikes, so intervals are wide in calm periods. The cost shows in the P90 pinball loss, which rises from 44.1 (raw) to 57.3.
- **What this means for the site.** The price forecast is useful as a calibrated, explained range for the next few days. Its P50 should not be presented as better than a standard exponential-smoothing forecast. The P50 errors are dominated by regime changes (origins 2023-11-21, 2024-01-05, 2024-10-01, 2024-11-15 and 2026-05-09 all have MASE above 3.5), which neither the model nor ETS anticipates.

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
- **No future weather or hydrology**: the forecasts do not use weather or inflow forecasts, only what is known at the origin. Rain or heat that is not yet visible in the lags is invisible to the model.
- **Holidays the package does not know**, such as ad hoc civic days, are treated as normal days.
- **ONI revisions**: stored ONI values are the latest NOAA revision, not the value first published. The backtest therefore sees slightly better ONI data than was available in real time, a small optimistic bias in the ONI features.
- **Explanations are local and approximate**: SHAP describes the P50 booster, contributions in kWh or COP do not add up exactly to the forecast, and feature correlations (reservoir and inflows, for example) spread credit between related features.
- **Small sample for the paired tests**: 24 origins. The demand result is robust; the price comparisons are not conclusive either way.

## What the model cannot do

It cannot forecast hourly prices, regional prices, or anything beyond 30 days for demand or 14 days for price. It cannot anticipate policy decisions, outages or rationing, and it gives no trading signal.

## Reproducibility

- `voltia train --predict` runs the backtest, fits the final models, stores them under `pipeline/models_store/<run_id>/` (LightGBM text files and a JSON manifest, no pickle) and writes the run, the forecasts and their drivers.
- `voltia predict` reforecasts from the latest settled day without retraining. `voltia anomalies` rebuilds the anomaly table.
- The randomness is fixed: LightGBM uses a seed, deterministic mode and a fixed thread count; Isolation Forest uses `random_state`. A test asserts that two training runs on the same data give identical metrics.
- Determinism was also checked on the real data: a second full run on a copy of the database reproduced the stored metrics exactly. A different LightGBM thread count can change the last digits.
