import "server-only";
import postgres from "postgres";
import { z } from "zod";
import { latestOf, pivotRows } from "./shape";
import {
  anomalySchema,
  briefingSchema,
  driverSchema,
  forecastBundleSchema,
  forecastPointSchema,
  isoDate,
  modelRunSchema,
  trackRowSchema,
  type Repository,
} from "./types";

type Sql = ReturnType<typeof postgres>;

// Timestamps are stored as naive UTC. Every SELECT converts them with AT TIME ZONE 'UTC', so the driver
// returns the right instant whatever the server's own time zone is.
const iso = (value: Date | string): string =>
  value instanceof Date ? value.toISOString() : new Date(value).toISOString();

const seriesRowSchema = z.object({ series: z.string(), day: isoDate, value: z.number() });
const optionalJson = <T extends z.ZodType>(schema: T) => schema.nullable().catch(null);

/**
 * PostgreSQL repository. It connects with the read-only role (db/migrations/0002_roles.pg.sql).
 * Every row passes through Zod, so a schema drift fails loudly instead of rendering wrong numbers.
 */
export function createPostgresRepository(sql: Sql): Repository {
  const seriesRows = async (names: readonly string[], from?: string, to?: string) => {
    const rows = await sql`
      SELECT series, to_char(day, 'YYYY-MM-DD') AS day, value
      FROM series_daily
      WHERE series IN ${sql([...names])}
        AND (${from ?? null}::date IS NULL OR day >= ${from ?? null}::date)
        AND (${to ?? null}::date IS NULL OR day <= ${to ?? null}::date)
      ORDER BY day`;
    return z.array(seriesRowSchema).parse(rows);
  };

  return {
    async series(names, range) {
      return pivotRows(await seriesRows(names, range?.from, range?.to), names);
    },

    async latest(names) {
      const rows = await sql`
        SELECT DISTINCT ON (series) series, to_char(day, 'YYYY-MM-DD') AS day, value
        FROM series_daily
        WHERE series IN ${sql([...names])}
        ORDER BY series, day DESC`;
      const parsed = z.array(seriesRowSchema).parse(rows);
      const frame = pivotRows(parsed, names);
      return latestOf(frame, names);
    },

    async forecast(target) {
      const rows = await sql`
        SELECT r.run_id, r.trained_at AT TIME ZONE 'UTC' AS trained_at, to_char(f.day, 'YYYY-MM-DD') AS day,
               f.horizon, f.p10, f.p50, f.p90, f.drivers
        FROM forecasts f
        JOIN (
          SELECT run_id, trained_at FROM model_runs m
          WHERE EXISTS (SELECT 1 FROM forecasts x WHERE x.run_id = m.run_id AND x.target = ${target})
          ORDER BY trained_at DESC LIMIT 1
        ) r ON r.run_id = f.run_id
        WHERE f.target = ${target}
        ORDER BY f.day`;
      if (rows.length === 0) return null;
      const first = rows[0] as { run_id: string; trained_at: Date | string };
      return forecastBundleSchema.parse({
        runId: first.run_id,
        target,
        trainedAt: iso(first.trained_at),
        points: rows.map((r) =>
          forecastPointSchema.parse({
            day: r.day,
            horizon: r.horizon,
            p10: r.p10,
            p50: r.p50,
            p90: r.p90,
            drivers: optionalJson(z.array(driverSchema)).parse(r.drivers),
          }),
        ),
      });
    },

    async anomalies({ target, limit }) {
      const rows = await sql`
        SELECT target, to_char(day, 'YYYY-MM-DD') AS day, severity, direction, method, detail
        FROM anomalies
        WHERE (${target ?? null}::text IS NULL OR target = ${target ?? null})
        ORDER BY severity DESC
        LIMIT ${limit}`;
      return z.array(anomalySchema).parse(rows);
    },

    async modelRun() {
      const rows = await sql`
        SELECT run_id, trained_at AT TIME ZONE 'UTC' AS trained_at, to_char(data_start, 'YYYY-MM-DD') AS data_start,
               to_char(data_end, 'YYYY-MM-DD') AS data_end, metrics, params
        FROM model_runs ORDER BY trained_at DESC LIMIT 1`;
      const r = rows[0];
      if (!r) return null;
      return modelRunSchema.parse({
        runId: r.run_id,
        trainedAt: iso(r.trained_at),
        dataStart: r.data_start,
        dataEnd: r.data_end,
        metrics: r.metrics,
        params: r.params,
      });
    },

    async briefing(lang) {
      const rows = await sql`
        SELECT to_char(day, 'YYYY-MM-DD') AS day, lang, body, source, created_at AT TIME ZONE 'UTC' AS created_at
        FROM briefings WHERE lang = ${lang} ORDER BY day DESC LIMIT 1`;
      const r = rows[0];
      return r ? briefingSchema.parse({ ...r, createdAt: iso(r.created_at) }) : null;
    },

    async hourly(series, days) {
      const rows = await sql`
        SELECT to_char(day, 'YYYY-MM-DD') AS day, hour, value
        FROM series_hourly
        WHERE series = ${series}
          AND day > (SELECT MAX(day) FROM series_hourly WHERE series = ${series}) - ${days}::int
        ORDER BY day, hour`;
      return z
        .array(z.object({ day: isoDate, hour: z.number().int(), value: z.number() }))
        .parse(rows);
    },

    async trackRecord(target) {
      try {
        const rows = await sql`
          SELECT to_char(l.origin, 'YYYY-MM-DD') AS origin, to_char(l.day, 'YYYY-MM-DD') AS day, l.horizon,
                 l.p10, l.p50, l.p90, a.value AS actual, n.value AS naive
          FROM forecast_log l
          LEFT JOIN series_daily a ON a.series = l.target AND a.day = l.day
          LEFT JOIN series_daily n ON n.series = l.target
            AND n.day = CASE WHEN l.target = 'demand_kwh' THEN l.day - 7 ELSE l.origin END
          WHERE l.target = ${target}
          ORDER BY l.day, l.origin`;
        return z.array(trackRowSchema).parse(rows);
      } catch (error) {
        // The table arrives with migration 0003, applied by the daily pipeline run.
        if ((error as { code?: string }).code === "42P01") return [];
        throw error;
      }
    },

    async health() {
      const datasets = await sql`
        SELECT dataset, to_char(last_day, 'YYYY-MM-DD') AS last_day, status, updated_at AT TIME ZONE 'UTC' AS updated_at, detail
        FROM ingest_log ORDER BY dataset`;
      const series = await sql`
        SELECT series, to_char(MAX(day), 'YYYY-MM-DD') AS last_day
        FROM series_daily GROUP BY series ORDER BY series`;
      return {
        source: "postgres" as const,
        generatedAt: new Date().toISOString(),
        datasets: datasets.map((d) => ({
          dataset: String(d.dataset),
          lastDay: d.last_day ? String(d.last_day) : null,
          status: d.status === "ok" ? ("ok" as const) : ("error" as const),
          updatedAt: iso(d.updated_at as Date | string),
          detail: d.detail ? String(d.detail) : null,
        })),
        series: series.map((s) => ({ series: String(s.series), lastDay: String(s.last_day) })),
      };
    },
  };
}

let client: Sql | undefined;

/** One small pooled connection per server instance; prepared statements are off for pooled hosts. */
export function getSql(url: string): Sql {
  client ??= postgres(url, { max: 1, prepare: false, idle_timeout: 20, connect_timeout: 10 });
  return client;
}
