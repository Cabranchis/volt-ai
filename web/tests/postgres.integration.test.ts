/**
 * Runs only when TEST_DATABASE_URL points at a database that went through `voltia migrate` and a
 * `voltia backfill` (with the read-only role's credentials, as in production). In CI it is skipped.
 *
 *   TEST_DATABASE_URL=postgresql://voltia_ro:...@127.0.0.1:5432/postgres npx vitest run tests/postgres
 */
import { afterAll, describe, expect, it } from "vitest";
import { createFixtureRepository } from "@/lib/data/fixtures";
import { createPostgresRepository, getSql } from "@/lib/data/postgres";
import { createPostgresLimiter } from "@/lib/ai/ratelimit";

const url = process.env.TEST_DATABASE_URL;

describe.skipIf(!url)("PostgreSQL repository with the read-only role", () => {
  const sql = getSql(url as string);
  const pg = createPostgresRepository(sql);

  afterAll(async () => {
    await sql.end({ timeout: 2 });
  });

  it("returns the same daily values as the JSON snapshot for the days both hold", async () => {
    const names = ["demand_kwh", "price_mean_cop_kwh", "reservoir_pct", "gen_thermal_kwh", "oni"];
    const range = { from: "2026-10-05", to: "2026-10-20" };
    const [fromDb, fromFixtures] = await Promise.all([
      pg.series(names, range),
      createFixtureRepository().series(names, range),
    ]);
    expect(fromDb.dates).toEqual(fromFixtures.dates);
    for (const name of names) {
      const a = fromDb.series[name] ?? [];
      const b = fromFixtures.series[name] ?? [];
      expect(a.length).toBe(b.length);
      a.forEach((value, i) => {
        const other = b[i] ?? null;
        if (value === null || other === null) expect(value).toBe(other);
        else expect(Math.abs(value - other), `${name} ${fromDb.dates[i]}`).toBeLessThan(Math.max(0.011, Math.abs(other) * 1e-6));
      });
    }
  });

  it("serialises dates as plain calendar days (no time-zone shift)", async () => {
    const latest = await pg.latest(["demand_kwh", "oni"]);
    expect(latest.demand_kwh?.day).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(latest.oni?.day).toBe("2026-08-01");
  });

  it("reports freshness per dataset and per series, labelled as the database", async () => {
    const health = await pg.health();
    expect(health.source).toBe("postgres");
    expect(health.datasets.map((d) => d.dataset).sort()).toEqual(
      ["oni", "weather", "xm_daily", "xm_generation", "xm_mix", "xm_price"],
    );
    expect(health.datasets.every((d) => d.status === "ok")).toBe(true);
    expect(health.series.find((s) => s.series === "demand_kwh")?.lastDay).toMatch(/^2026-10-/);
  });

  it("returns hourly values for the latest days", async () => {
    const rows = await pg.hourly("price_cop_kwh", 3);
    expect(rows.length).toBeGreaterThanOrEqual(24);
    expect(new Set(rows.map((r) => r.day)).size).toBeLessThanOrEqual(3);
  });

  it("answers null for things the pipeline has not produced yet, instead of failing", async () => {
    // These tables are empty or hold other data in a fresh database; the repository must not throw.
    await expect(pg.briefing("es")).resolves.toSatisfy((v: unknown) => v === null || typeof v === "object");
    await expect(pg.anomalies({ limit: 5 })).resolves.toBeInstanceOf(Array);
  });

  it("cannot write to data tables, but the rate limiter can write its own", async () => {
    await expect(sql`INSERT INTO series_daily VALUES ('x', '2026-01-01', 1)`).rejects.toThrow(/permission denied/);
    await expect(sql`UPDATE ingest_log SET status = 'ok'`).rejects.toThrow(/permission denied/);

    const limiter = createPostgresLimiter(sql as never);
    const key = `it-${Date.now()}`;
    const results = [];
    for (let i = 0; i < 4; i++) results.push(await limiter.hit(key, 3, 600));
    expect(results.map((r) => r.allowed)).toEqual([true, true, true, false]);
    await sql`DELETE FROM rate_limits WHERE client_key LIKE ${`${key}%`}`;
  });
});
