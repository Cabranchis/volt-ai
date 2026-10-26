# Data dictionary

All daily values live in `series_daily (series, day, value)`; hourly values in `series_hourly (series, day, hour, value)`. Dates are calendar dates in Colombia (UTC-5, no daylight saving). Plausible ranges are enforced in [`pipeline/src/voltia/schemas.py`](../pipeline/src/voltia/schemas.py).

## Daily series

| Series | Meaning | Unit | Source (metric) | Notes |
| --- | --- | --- | --- | --- |
| `demand_kwh` | National electricity demand (SIN) | kWh/day | XM `DemaSIN` | Held back until it reconciles with generation (ADR 0009) |
| `price_mean_cop_kwh` | Mean of the 24 hourly spot prices | COP/kWh | XM `PrecBolsNaci` | Simple mean, not volume weighted |
| `price_max_cop_kwh` | Highest hourly spot price of the day | COP/kWh | XM `PrecBolsNaci` | |
| `reservoir_pct` | Useful reservoir volume, system | fraction 0..1 | XM `PorcVoluUtilDiar` | |
| `reservoir_kwh` | Useful reservoir volume, system | kWh of energy | XM `VoluUtilDiarEner` | |
| `inflows_kwh` | Hydrological inflows, system | kWh/day | XM `AporEner` | |
| `inflows_pct` | Inflows relative to the historical mean | ratio (1.0 = mean) | XM `PorcApor` | Can exceed 1 |
| `inflows_hist_mean_kwh` | Historical mean inflows for that day | kWh/day | XM `AporEnerMediHist` | |
| `gen_total_kwh` | Total generation, system | kWh/day | XM `Gene` (Sistema) | Only complete 24-hour days |
| `gen_hydro_kwh` | Generation by hydro plants | kWh/day | XM `Gene` (Recurso) + `ListadoRecursos` | |
| `gen_thermal_kwh` | Generation by thermal plants | kWh/day | same | |
| `gen_solar_kwh` | Generation by solar plants | kWh/day | same | Resource types `SOLAR` and `Solar` are merged |
| `gen_wind_kwh` | Generation by wind plants | kWh/day | same | |
| `gen_cogen_kwh` | Generation by cogenerators | kWh/day | same | |
| `gen_other_kwh` | Resources missing from the current catalogue | kWh/day | same | About 1.4 % in early 2018, 0 % since 2022 (retired plants) |
| `weather_temp_c` | Mean temperature, average of Bogotá, Medellín, Cali, Barranquilla | °C | Open-Meteo | |
| `weather_precip_mm` | Precipitation, average of the same four cities | mm | Open-Meteo | |
| `oni` | Oceanic Niño Index (3-month season), stored on the first day of the central month | °C anomaly | NOAA CPC | Monthly; values above +0.5 sustained are El Niño |
| `dispatch_cost` | Marginal cost of the programmed dispatch, mean of the 24 hours | COP/kWh | XM `CostMargDesp` | Programmed the day before it applies, so it is known for days XM has not settled yet (ADR 0012) |
| `scarcity_price` | Scarcity price | COP/kWh | XM `PrecEsca` | Published about 3 days late |
| `contract_price` | Average contract price, all markets | COP/kWh | XM `PrecPromCont` | Published about 5 days late; has gaps of weeks |
| `contract_price_unreg` | Average contract price, unregulated market, mean of the 24 hours | COP/kWh | XM `PrecPromContNoRegu` | Same gaps as `contract_price` |
| `spill_kwh` | Energy spilled by the reservoirs | kWh/day | XM `VertEner` | XM lists only days with spilling; days with a turbined volume and no listing are stored as 0 |
| `turbined_m3` | Water turbined by the hydro plants | m³/day | XM `VolTurbMasa` | |
| `reservoir_capacity_kwh` | Usable reservoir capacity, system | kWh of energy | XM `CapaUtilDiarEner` | |

## Hourly series (last 90 days only)

| Series | Meaning | Unit |
| --- | --- | --- |
| `price_cop_kwh` | Hourly national spot price | COP/kWh |
| `generation_kwh` | Hourly system generation | kWh |

## Other tables

| Table | Purpose |
| --- | --- |
| `model_runs` | One row per training run: dates, backtest metrics (model and baselines), parameters |
| `forecasts` | P10/P50/P90 per target and day, with top SHAP drivers |
| `anomalies` | Atypical days per target with severity, direction and method |
| `briefings` | Daily executive summary per language and its origin (`gemini` or `template`) |
| `rate_limits` | Counters for the chat endpoint |
| `ingest_log` | Last outcome per dataset (`xm_daily`, `xm_price`, `xm_market`, `xm_contracts`, `xm_generation`, `xm_mix`, `weather`, `oni`) |
