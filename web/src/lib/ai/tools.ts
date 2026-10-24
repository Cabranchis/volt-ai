import { tool } from "ai";
import { z } from "zod";
import { getAnomalies, getForecast, getSeries } from "@/lib/data";
import { isoDate, seriesNameSchema, type ForecastTarget } from "@/lib/data/types";
import { featureLabel } from "@/lib/feature-labels";
import type { Locale } from "@/lib/i18n/config";
import { MIX_SERIES_NAMES } from "@/lib/insights";
import { comparePeriods, display, lastTimeAtOrAbove, SERIES_META, snapshot, summariseSeries } from "./analytics";

const SNAPSHOT_SERIES = [
  "demand_kwh",
  "price_mean_cop_kwh",
  "reservoir_pct",
  "inflows_pct",
  "oni",
  ...MIX_SERIES_NAMES,
];

const TARGET_OF = { demand: "demand_kwh", price: "price_mean_cop_kwh" } as const satisfies Record<string, ForecastTarget>;
const targetName = z.enum(["demand", "price"]);
const period = z.object({ from: isoDate, to: isoDate }).describe("Inclusive calendar period, ISO dates.");

/** Every tool answers with a plain error object instead of throwing, so the model can explain the gap. */
async function guarded<T>(run: () => Promise<T>): Promise<T | { error: string }> {
  try {
    return await run();
  } catch {
    return { error: "The data could not be read right now." };
  }
}

/**
 * The analyst's whole reach. Each tool reads cached data through the same accessors as the pages,
 * validates its arguments with Zod, and returns compact, already-converted numbers.
 * There is deliberately no tool that accepts SQL or a free-form query (ADR 0006).
 */
export function buildTools(locale: Locale) {
  return {
    current_snapshot: tool({
      description:
        "Latest demand, spot price, reservoir level, inflows and El Niño index, each with its value a week earlier and on the same day last year, plus the generation mix now and a year ago. Start here for any question about 'now' or 'this week'.",
      inputSchema: z.object({}),
      execute: () => guarded(async () => snapshot(await getSeries(SNAPSHOT_SERIES))),
    }),

    series_summary: tool({
      description:
        "Summary of one daily series over a period: first, last, minimum and maximum (with dates), mean and about 24 sample points. Values are in the stated unit. Use it for trends and extremes.",
      inputSchema: z.object({
        series: seriesNameSchema,
        from: isoDate.optional(),
        to: isoDate.optional(),
      }),
      execute: ({ series, from, to }) =>
        guarded(async () => summariseSeries(await getSeries([series]), series, from, to)),
    }),

    compare_periods: tool({
      description:
        "Mean of one series in period A and in period B, and the percentage change from A to B. Use it for 'this week versus last week' or 'now versus a year ago'.",
      inputSchema: z.object({ series: seriesNameSchema, a: period, b: period }),
      execute: ({ series, a, b }) =>
        guarded(async () => comparePeriods(await getSeries([series]), series, a, b)),
    }),

    last_time_at_or_above: tool({
      description:
        "Most recent earlier day when a series was at or above a threshold (default: its latest value), and how many days in the last year were. Answers 'when was the price last this high?'. The threshold is in the series' display unit.",
      inputSchema: z.object({ series: seriesNameSchema, threshold: z.number().finite().optional() }),
      execute: ({ series, threshold }) =>
        guarded(async () => lastTimeAtOrAbove(await getSeries([series]), series, threshold)),
    }),

    get_forecast: tool({
      description:
        "Forecast from the latest training run: for each of the next days, the median (P50) and an 80 % range (P10 to P90), plus the top factors behind the first day. Demand is in GWh/day, price in COP/kWh.",
      inputSchema: z.object({ target: targetName, days: z.number().int().min(1).max(30).default(7) }),
      execute: ({ target, days }) =>
        guarded(async () => {
          const key = TARGET_OF[target];
          const forecast = await getForecast(key);
          if (!forecast) return { error: "There is no forecast yet." };
          const unit = SERIES_META[key].unit;
          const first = forecast.points[0];
          return {
            target,
            unit,
            trainedAt: forecast.trainedAt,
            days: forecast.points.slice(0, days).map((p) => ({
              day: p.day,
              p10: display(key, p.p10),
              p50: display(key, p.p50),
              p90: display(key, p.p90),
            })),
            topFactorsFirstDay: (first?.drivers ?? []).slice(0, 4).map((d) => ({
              factor: featureLabel(d.feature, locale),
              effect: d.direction === "up" ? "raises" : "lowers",
              amount: display(key, Math.abs(d.contribution)),
            })),
          };
        }),
    }),

    list_anomalies: tool({
      description:
        "The most unusual days for demand or price, most severe first, with direction (higher or lower than expected) and, when known, the observed and expected values.",
      inputSchema: z.object({ target: targetName.optional(), limit: z.number().int().min(1).max(10).default(5) }),
      execute: ({ target, limit }) =>
        guarded(async () => {
          const rows = await getAnomalies(limit, target ? TARGET_OF[target] : undefined);
          return rows.map((a) => {
            const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? display(a.target, v) : null);
            return {
              day: a.day,
              target: a.target === "demand_kwh" ? "demand" : "price",
              severity: Math.round(a.severity * 10) / 10,
              direction: a.direction === "high" ? "higher than expected" : "lower than expected",
              unit: SERIES_META[a.target].unit,
              observed: num(a.detail?.["observed"]),
              expected: num(a.detail?.["expected"]),
            };
          });
        }),
    }),
  };
}

export type AnalystTools = ReturnType<typeof buildTools>;
