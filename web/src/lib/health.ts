import type { Health } from "@/lib/data/types";

/**
 * What the health endpoint says about the platform, decided from the stored facts.
 *
 * - `degraded`: something is broken now: a dataset failed to load, there is no record of any
 *   dataset or model, or production is serving the bundled snapshot instead of the database.
 * - `stale`: nothing failed, but the data or the forecast is older than the pipeline would leave it:
 *   the pipeline stopped (or was stopped by the publication gate) and nobody has fixed it yet.
 * - `ok`: neither.
 *
 * A reader of the site is never left to find out by themselves that a forecast is old.
 */
export type HealthStatus = "ok" | "stale" | "degraded";

/** XM publishes the complete price about three days late, so five days without a new day is a stop. */
export const MAX_DATA_AGE_DAYS = 5;
/** The pipeline trains two or three times a day; two days without a new run is a failing pipeline. */
export const MAX_MODEL_AGE_DAYS = 3;
export const MAX_FORECAST_AGE_DAYS = 2;

const TARGET_SERIES = ["demand_kwh", "price_mean_cop_kwh"] as const;
const DAY_MS = 86_400_000;

export type HealthReason =
  | "dataset_error"
  | "optional_dataset_error"
  | "optional_dataset_stale"
  | "no_datasets"
  | "no_model"
  | "snapshot_in_production"
  | "data_stale"
  | "model_stale"
  | "forecast_stale";

export interface HealthAssessment {
  status: HealthStatus;
  reasons: HealthReason[];
  /** Whole days, or null when there is nothing to measure. */
  ages: { dataDays: number | null; modelDays: number | null; forecastDays: number | null };
}

const bogotaDay = (date: Date): string => new Intl.DateTimeFormat("en-CA", { timeZone: "America/Bogota" }).format(date);

/**
 * Calendar days in Bogotá, the way the age badge on the forecast pages counts them, so the status
 * and the badge turn on the same day. A date-only value ("2026-11-11") is already a Bogotá day.
 */
const daysSince = (iso: string | null, now: Date): number | null => {
  if (!iso) return null;
  const time = Date.parse(iso);
  if (!Number.isFinite(time)) return null;
  const day = iso.length === 10 ? iso : bogotaDay(new Date(time));
  const diff = (Date.parse(`${bogotaDay(now)}T00:00:00Z`) - Date.parse(`${day}T00:00:00Z`)) / DAY_MS;
  return Math.max(Math.round(diff), 0);
};

/**
 * Datasets the model can do without for a while (the same list as OPTIONAL_DATASETS in the
 * pipeline). A failure of one is reported, but only a long silence makes the platform `stale`: they
 * fail now and then on their own (a forecast with missing values is refused on purpose) and a page
 * to the owner for each would teach them to ignore the page. The days are the gate's limits.
 */
const OPTIONAL_MAX_AGE_DAYS: Record<string, number> = {
  xm_market: 10,
  xm_contracts: 10,
  xm_regional: 10,
  weather_forecast: 10,
  weather: 30,
  oni: 150,
};

export function assessHealth(
  health: Health,
  now: Date = new Date(),
  production: boolean = process.env.VERCEL_ENV === "production",
): HealthAssessment {
  const degraded: HealthReason[] = [];
  const stale: HealthReason[] = [];

  if (health.datasets.length === 0) degraded.push("no_datasets");
  const failed = health.datasets.filter((d) => d.status === "error");
  if (failed.some((d) => !(d.dataset in OPTIONAL_MAX_AGE_DAYS))) degraded.push("dataset_error");
  const optionalFailed = failed.some((d) => d.dataset in OPTIONAL_MAX_AGE_DAYS);
  const optionalSilent = health.datasets.some((d) => {
    const limit = OPTIONAL_MAX_AGE_DAYS[d.dataset];
    const age = limit === undefined ? null : daysSince(d.lastDay, now);
    return age !== null && age > limit;
  });
  if (production && health.source === "fixtures") degraded.push("snapshot_in_production");

  // The newest day of the older target: the forecast of both needs both.
  const lastDays = TARGET_SERIES.map((name) => health.series.find((s) => s.series === name)?.lastDay ?? null);
  const dataDays = lastDays.some((d) => d === null)
    ? null
    : Math.max(...lastDays.map((d) => daysSince(d, now) ?? 0));
  const modelDays = daysSince(health.model.trainedAt, now);
  const forecastDays = daysSince(health.forecast.issuedAt, now);

  if (health.source === "postgres" && health.model.trainedAt === null) degraded.push("no_model");
  if (dataDays !== null && dataDays > MAX_DATA_AGE_DAYS) stale.push("data_stale");
  if (modelDays !== null && modelDays > MAX_MODEL_AGE_DAYS) stale.push("model_stale");
  if (forecastDays !== null && forecastDays > MAX_FORECAST_AGE_DAYS) stale.push("forecast_stale");

  if (optionalSilent) stale.push("optional_dataset_stale");
  const notes: HealthReason[] = optionalFailed && !optionalSilent ? ["optional_dataset_error"] : [];

  const status: HealthStatus = degraded.length > 0 ? "degraded" : stale.length > 0 ? "stale" : "ok";
  return { status, reasons: [...degraded, ...stale, ...notes], ages: { dataDays, modelDays, forecastDays } };
}

/**
 * The public reason a dataset failed, from the stored exception text. The text itself (an exception
 * type, a message from a source, sometimes a URL) is not published: it says nothing a reader can
 * act on and tells an attacker how the pipeline is built.
 */
export type FailureReason = "upstream_unreachable" | "validation_rejected" | "error";

export function failureReason(detail: string | null): FailureReason {
  if (!detail) return "error";
  if (/timeout|timed out|ConnectError|ConnectionError|ReadError|WriteError|RemoteProtocolError|TransportError|XMTransientError|NetworkError|Server error|status (5\d\d|429)/i.test(detail)) {
    return "upstream_unreachable";
  }
  if (/BatchValidationError|schema violations|series missing|dated after|duplicated rows|no data for the requested range|gap of/i.test(detail)) {
    return "validation_rejected";
  }
  return "error";
}
