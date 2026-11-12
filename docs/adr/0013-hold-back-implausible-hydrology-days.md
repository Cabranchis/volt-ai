# ADR 0013: Hold back hydrology days that XM published half finished

Status: accepted (2026-11-12)

## Context
ADR 0009 recorded that the hydrology series were complete on 2026-10-24 and held back only demand and the hourly metrics. On 2026-11-12 at 11:09 UTC the daily ingest stored a hydrology day that XM had published before finishing it:

| Series, 2026-11-11 | Day before | Value stored |
| --- | --- | --- |
| `reservoir_pct` | 0.79068 | 0.07639 |
| `reservoir_kwh` | 13.967e9 | 1.351e9 |
| `inflows_pct` | 0.432 | 0.054 |

It passes every range check (a level of 0.076 is a number between 0 and 1). For a few hours the Hydrology page showed "Reservoir level 7.6 %, -70.4 points against seven days earlier" and the price model read the change as a driver (`reservoir_now_chg`, +21 COP/kWh on the first day by SHAP). Later the same day XM served the finished value (0.78737) and a manual pipeline run replaced the stored one; with the finished value the price forecast moved by 3 COP/kWh on the first day and 6 on the fourteenth, so the effect on the forecast was small, but the page was wrong.

## Decision
- A daily hydrology value is accepted only if, compared with the last accepted day, the stored volume (`reservoir_kwh`), its percentage (`reservoir_pct`) and the capacity (`reservoir_capacity_kwh`) stay between 0.85 and 1.15 times, and the inflows (`inflows_kwh`, `inflows_pct`) are at least 0.25 times.
- The limits come from the history: over 3 220 days from 2018 the daily ratio of the volume was between 0.9546 and 1.0518 (its percentage 0.9724 to 1.0518), of the capacity between 0.9658 and 1.0313, and of the inflows never below 0.452. The incident was 0.097 for the volume and 0.126 for the inflows. The limits leave about three times the range for the volume and the capacity. The inflows have only a lower limit, which catches drops of more than 75 %, because they vary a lot from day to day. Each metric is a separate XM request, so each guarded series is checked on its own: a percentage can exist for a day whose volume does not yet.
- The series of a group come from one publication: when one fails, that day is dropped for all of them (`plausible_hydrology` in `voltia/ingest.py`).
- The first day of a batch has nothing to compare with and is kept. Later days are compared with the last accepted day, so two bad days in a row do not validate each other.
- A warning `ingest.hydrology.implausible_days_dropped` lists the days and the reason. The next update re-reads the last 7 days and stores the day once XM has finished it.

## Consequences
- The newest hydrology day can lag by a day when XM publishes it early, as demand already does.
- Dropped days are not deleted from the database: up to 3 dropped days in the middle of a batch leave a gap that the continuity check accepts (`MAX_GAP_DAYS`), and the stored value of those days stays until XM serves a plausible one. More than 3 consecutive gaps fail the batch.
- A real jump beyond the limits (never seen in eight years) would not confirm itself: later days are compared with the last accepted day, so they are held back too, until the jump day becomes the first day of a 7-day re-read window, about a week later. Hydrology would lag by that time. This follows from not letting two bad days validate each other.

## Rejected alternatives
- Reconcile with the sum of the per-reservoir values (like demand with generation): the regional dataset runs on its own and may be partial at the same time.
- Drop the newest N days always: rejected in ADR 0009 for the same reasons.
- Filter on read, in `db.read_series` and in the web app: it leaves the wrong value stored and duplicates the rule in two languages.
- A moving z-score: less stable with regime changes than limits at three times the historical range.
