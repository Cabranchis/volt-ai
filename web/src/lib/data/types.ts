import { z } from "zod";

/** Daily series stored by the pipeline (docs/data-dictionary.md). */
export const SERIES_NAMES = [
  "demand_kwh",
  "price_mean_cop_kwh",
  "price_max_cop_kwh",
  "reservoir_pct",
  "reservoir_kwh",
  "inflows_kwh",
  "inflows_pct",
  "inflows_hist_mean_kwh",
  "gen_total_kwh",
  "gen_hydro_kwh",
  "gen_thermal_kwh",
  "gen_solar_kwh",
  "gen_wind_kwh",
  "gen_cogen_kwh",
  "gen_other_kwh",
  "weather_temp_c",
  "weather_precip_mm",
  "oni",
] as const;
export type SeriesName = (typeof SERIES_NAMES)[number];
export const seriesNameSchema = z.enum(SERIES_NAMES);

export const FORECAST_TARGETS = ["demand_kwh", "price_mean_cop_kwh"] as const;
export type ForecastTarget = (typeof FORECAST_TARGETS)[number];
export const forecastTargetSchema = z.enum(FORECAST_TARGETS);

export const isoDate = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/)
  .refine((s) => {
    const t = Date.parse(s);
    return !Number.isNaN(t) && new Date(t).toISOString().startsWith(s);
  }, "not a calendar date");

/** Columnar daily data: one shared date axis, one array per series (null where missing). */
export const seriesFrameSchema = z.object({
  dates: z.array(isoDate),
  series: z.record(z.string(), z.array(z.number().nullable())),
});
export type SeriesFrame = z.infer<typeof seriesFrameSchema>;

export const latestPointSchema = z.object({ day: isoDate, value: z.number() });
export type LatestPoint = z.infer<typeof latestPointSchema>;

export const driverSchema = z.object({
  feature: z.string(),
  contribution: z.number(),
  direction: z.enum(["up", "down"]),
});
export type Driver = z.infer<typeof driverSchema>;

export const forecastPointSchema = z.object({
  day: isoDate,
  horizon: z.number().int().min(1),
  p10: z.number(),
  p50: z.number(),
  p90: z.number(),
  drivers: z.array(driverSchema).nullable(),
});
export type ForecastPoint = z.infer<typeof forecastPointSchema>;

export const forecastBundleSchema = z.object({
  runId: z.string(),
  target: forecastTargetSchema,
  trainedAt: z.string(),
  points: z.array(forecastPointSchema),
});
export type ForecastBundle = z.infer<typeof forecastBundleSchema>;

export const anomalySchema = z.object({
  target: forecastTargetSchema,
  day: isoDate,
  severity: z.number().min(0),
  direction: z.enum(["high", "low"]),
  method: z.string(),
  detail: z.record(z.string(), z.unknown()).nullable(),
});
export type Anomaly = z.infer<typeof anomalySchema>;

export const modelRunSchema = z.object({
  runId: z.string(),
  trainedAt: z.string(),
  dataStart: isoDate,
  dataEnd: isoDate,
  metrics: z.record(z.string(), z.unknown()),
  params: z.record(z.string(), z.unknown()),
});
export type ModelRun = z.infer<typeof modelRunSchema>;

export const briefingSchema = z.object({
  day: isoDate,
  lang: z.enum(["es", "en"]),
  body: z.string(),
  source: z.enum(["gemini", "template"]),
  createdAt: z.string(),
});
export type Briefing = z.infer<typeof briefingSchema>;

export const hourlyPointSchema = z.object({
  day: isoDate,
  hour: z.number().int().min(1).max(24),
  value: z.number(),
});
export type HourlyPoint = z.infer<typeof hourlyPointSchema>;

/**
 * One forecast from forecast_log (as first issued) next to what happened. `actual` is null while XM
 * has not settled the day. `naive` is the reference a forecaster must beat: the same weekday of the
 * previous week for demand, the last settled price at the origin for the price.
 */
export const trackRowSchema = z.object({
  origin: isoDate,
  day: isoDate,
  horizon: z.number().int().min(1),
  p10: z.number(),
  p50: z.number(),
  p90: z.number(),
  actual: z.number().nullable(),
  naive: z.number().nullable(),
});
export type TrackRow = z.infer<typeof trackRowSchema>;

/**
 * Reservoirs and rivers by hydrological region (table entity_daily). `reservoirs` is the latest day
 * XM has settled; `history` aggregates each region by day: the share of its reservoirs' capacity that
 * is full, and its rivers' inflow as a share of their historical mean for that day.
 */
export const regionalSchema = z.object({
  day: isoDate,
  reservoirs: z.array(
    z.object({
      name: z.string(),
      region: z.string(),
      volumeKwh: z.number(),
      capacityKwh: z.number(),
      weekAgoKwh: z.number().nullable(),
    }),
  ),
  history: z.object({
    dates: z.array(isoDate),
    regions: z.record(
      z.string(),
      z.object({
        reservoirPct: z.array(z.number().nullable()),
        inflowPct: z.array(z.number().nullable()),
      }),
    ),
  }),
});
export type RegionalData = z.infer<typeof regionalSchema>;

export const dataSourceSchema = z.enum(["postgres", "fixtures"]);
export type DataSource = z.infer<typeof dataSourceSchema>;

export const healthSchema = z.object({
  source: dataSourceSchema,
  generatedAt: z.string(),
  datasets: z.array(
    z.object({
      dataset: z.string(),
      lastDay: isoDate.nullable(),
      status: z.enum(["ok", "error"]),
      updatedAt: z.string(),
      detail: z.string().nullable(),
    }),
  ),
  series: z.array(z.object({ series: z.string(), lastDay: isoDate })),
});
export type Health = z.infer<typeof healthSchema>;

export interface SeriesRange {
  from?: string;
  to?: string;
}

/** Everything the app reads. Implemented by PostgreSQL and by JSON fixtures (ADR 0008). */
export interface Repository {
  series(names: readonly string[], range?: SeriesRange): Promise<SeriesFrame>;
  latest(names: readonly string[]): Promise<Record<string, LatestPoint | null>>;
  forecast(target: ForecastTarget): Promise<ForecastBundle | null>;
  anomalies(opts: { target?: ForecastTarget; limit: number }): Promise<Anomaly[]>;
  modelRun(): Promise<ModelRun | null>;
  briefing(lang: "es" | "en"): Promise<Briefing | null>;
  hourly(series: string, days: number): Promise<HourlyPoint[]>;
  trackRecord(target: ForecastTarget): Promise<TrackRow[]>;
  regional(): Promise<RegionalData | null>;
  health(): Promise<Health>;
}
