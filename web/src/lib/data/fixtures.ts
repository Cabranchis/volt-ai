import anomaliesJson from "./fixtures/anomalies.json";
import briefingsJson from "./fixtures/briefings.json";
import forecastsJson from "./fixtures/forecasts.json";
import healthJson from "./fixtures/health.json";
import hourlyJson from "./fixtures/hourly.json";
import modelRunJson from "./fixtures/model-run.json";
import seriesJson from "./fixtures/series.json";
import { latestOf, sliceFrame } from "./shape";
import {
  anomalySchema,
  briefingSchema,
  forecastBundleSchema,
  healthSchema,
  hourlyPointSchema,
  modelRunSchema,
  seriesFrameSchema,
  type ForecastBundle,
  type Repository,
} from "./types";
import { z } from "zod";

/**
 * Repository backed by JSON snapshots exported from the real database (tools/export_fixtures.py).
 * Used for tests, local development and pull-request previews, which need no secrets.
 */
export function createFixtureRepository(): Repository {
  const frame = seriesFrameSchema.parse(seriesJson);
  const forecasts = z.record(z.string(), forecastBundleSchema).parse(forecastsJson);
  const anomalies = z.array(anomalySchema).parse(anomaliesJson);
  const briefings = z.array(briefingSchema).parse(briefingsJson);
  const modelRun = modelRunSchema.nullable().parse(modelRunJson);
  const hourly = z.array(hourlyPointSchema.extend({ series: z.string() })).parse(hourlyJson);
  const health = healthSchema.omit({ source: true }).parse(healthJson);

  return {
    async series(names, range) {
      return sliceFrame(frame, names, range);
    },
    async latest(names) {
      return latestOf(frame, names);
    },
    async forecast(target): Promise<ForecastBundle | null> {
      return forecasts[target] ?? null;
    },
    async anomalies({ target, limit }) {
      return anomalies.filter((a) => !target || a.target === target).slice(0, limit);
    },
    async modelRun() {
      return modelRun;
    },
    async briefing(lang) {
      return briefings.find((b) => b.lang === lang) ?? null;
    },
    async hourly(series, days) {
      const rows = hourly.filter((r) => r.series === series);
      const lastDay = rows.reduce((max, r) => (r.day > max ? r.day : max), "");
      const cutoff = new Date(`${lastDay}T00:00:00Z`);
      cutoff.setUTCDate(cutoff.getUTCDate() - (days - 1));
      const from = cutoff.toISOString().slice(0, 10);
      return rows
        .filter((r) => r.day >= from)
        .map(({ day, hour, value }) => ({ day, hour, value }));
    },
    async health() {
      return { ...health, source: "fixtures" as const };
    },
  };
}
