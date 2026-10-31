import { cacheLife, cacheTag } from "next/cache";
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
  RegionalData,
  SeriesFrame,
  TrackRow,
} from "./types";

/*
 * Cached read accessors used by pages and route handlers.
 * Every accessor carries DATA_TAG, so the pipeline can expire all of them at once the moment it
 * finishes (POST /api/revalidate). Without that, the first visitor after a quiet period is served
 * the old copy while the new one is built (see docs/architecture.md).
 */
export const DATA_TAG = "data";

export async function getSeries(
  names: string[],
  from?: string,
  to?: string,
): Promise<SeriesFrame> {
  "use cache";
  cacheLife("hours");
  cacheTag(DATA_TAG);
  return (await getRepository()).series(names, { from, to });
}

export async function getLatest(names: string[]): Promise<Record<string, LatestPoint | null>> {
  "use cache";
  cacheLife("hours");
  cacheTag(DATA_TAG);
  return (await getRepository()).latest(names);
}

export async function getForecast(target: ForecastTarget): Promise<ForecastBundle | null> {
  "use cache";
  cacheLife("hours");
  cacheTag(DATA_TAG);
  return (await getRepository()).forecast(target);
}

export async function getAnomalies(limit: number, target?: ForecastTarget): Promise<Anomaly[]> {
  "use cache";
  cacheLife("hours");
  cacheTag(DATA_TAG);
  return (await getRepository()).anomalies({ target, limit });
}

export async function getModelRun(): Promise<ModelRun | null> {
  "use cache";
  cacheLife("hours");
  cacheTag(DATA_TAG);
  return (await getRepository()).modelRun();
}

export async function getBriefing(lang: "es" | "en"): Promise<Briefing | null> {
  "use cache";
  cacheLife("hours");
  cacheTag(DATA_TAG);
  return (await getRepository()).briefing(lang);
}

export async function getHourly(series: string, days: number): Promise<HourlyPoint[]> {
  "use cache";
  cacheLife("hours");
  cacheTag(DATA_TAG);
  return (await getRepository()).hourly(series, days);
}

export async function getTrackRecord(target: ForecastTarget): Promise<TrackRow[]> {
  "use cache";
  cacheLife("hours");
  cacheTag(DATA_TAG);
  return (await getRepository()).trackRecord(target);
}

export async function getRegional(): Promise<RegionalData | null> {
  "use cache";
  cacheLife("hours");
  cacheTag(DATA_TAG);
  return (await getRepository()).regional();
}

export async function getHealth(): Promise<Health> {
  "use cache";
  cacheLife("minutes");
  cacheTag(DATA_TAG);
  return (await getRepository()).health();
}
