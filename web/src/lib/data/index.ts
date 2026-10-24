import { cacheLife } from "next/cache";
import { getRepository } from "./repository";
import type {
  Anomaly,
  Briefing,
  ForecastBundle,
  ForecastTarget,
  Health,
  HourlyPoint,
  LatestPoint,
  ModelRun,
  SeriesFrame,
} from "./types";

/*
 * Cached read accessors used by pages and route handlers.
 * The pipeline runs once a day, so an hour of caching is conservative (see docs/architecture.md).
 */

export async function getSeries(
  names: string[],
  from?: string,
  to?: string,
): Promise<SeriesFrame> {
  "use cache";
  cacheLife("hours");
  return (await getRepository()).series(names, { from, to });
}

export async function getLatest(names: string[]): Promise<Record<string, LatestPoint | null>> {
  "use cache";
  cacheLife("hours");
  return (await getRepository()).latest(names);
}

export async function getForecast(target: ForecastTarget): Promise<ForecastBundle | null> {
  "use cache";
  cacheLife("hours");
  return (await getRepository()).forecast(target);
}

export async function getAnomalies(limit: number, target?: ForecastTarget): Promise<Anomaly[]> {
  "use cache";
  cacheLife("hours");
  return (await getRepository()).anomalies({ target, limit });
}

export async function getModelRun(): Promise<ModelRun | null> {
  "use cache";
  cacheLife("hours");
  return (await getRepository()).modelRun();
}

export async function getBriefing(lang: "es" | "en"): Promise<Briefing | null> {
  "use cache";
  cacheLife("hours");
  return (await getRepository()).briefing(lang);
}

export async function getHourly(series: string, days: number): Promise<HourlyPoint[]> {
  "use cache";
  cacheLife("hours");
  return (await getRepository()).hourly(series, days);
}

export async function getHealth(): Promise<Health> {
  "use cache";
  cacheLife("minutes");
  return (await getRepository()).health();
}
