import { describe, expect, it } from "vitest";
import type { Health } from "@/lib/data/types";
import { assessHealth, failureReason, MAX_DATA_AGE_DAYS } from "./health";

const NOW = new Date("2026-11-15T12:00:00Z");
const daysAgo = (n: number) => new Date(NOW.getTime() - n * 86_400_000).toISOString();
const day = (n: number) => daysAgo(n).slice(0, 10);
const series = (demand: number, price: number) => [
  { series: "demand_kwh", lastDay: day(demand) },
  { series: "price_mean_cop_kwh", lastDay: day(price) },
];

function health(over: Partial<Health> = {}): Health {
  return {
    source: "postgres",
    generatedAt: NOW.toISOString(),
    datasets: [{ dataset: "xm_daily", lastDay: day(3), status: "ok", updatedAt: daysAgo(0), detail: null }],
    series: series(3, 4),
    model: { trainedAt: daysAgo(0) },
    forecast: { issuedAt: daysAgo(0) },
    ...over,
  };
}

const failing = (dataset: string) => ({ dataset, lastDay: day(3), status: "error" as const, updatedAt: daysAgo(0), detail: "x" });

describe("assessHealth", () => {
  it("is ok when the data is a few days old (XM publishes late), the model and forecast are from today", () => {
    expect(assessHealth(health(), NOW, true)).toEqual({
      status: "ok",
      reasons: [],
      ages: { dataDays: 4, modelDays: 0, forecastDays: 0 },
    });
  });

  it("is degraded when a dataset failed, whatever its age", () => {
    const result = assessHealth(health({ datasets: [failing("xm_price")] }), NOW, true);
    expect(result.status).toBe("degraded");
    expect(result.reasons).toEqual(["dataset_error"]);
  });

  it("is degraded when nothing is recorded: no dataset, or no training run in the database", () => {
    expect(assessHealth(health({ datasets: [] }), NOW, true).reasons).toContain("no_datasets");
    const noRun = assessHealth(health({ model: { trainedAt: null }, forecast: { issuedAt: null } }), NOW, true);
    expect(noRun.status).toBe("degraded");
    expect(noRun.reasons).toContain("no_model");
  });

  it("is degraded when production serves the snapshot, and only in production", () => {
    const snapshot = health({ source: "fixtures" });
    expect(assessHealth(snapshot, NOW, true).reasons).toContain("snapshot_in_production");
    expect(assessHealth(snapshot, NOW, false).reasons).not.toContain("snapshot_in_production");
  });

  it("is stale, not degraded, when the data or the forecast is older than the pipeline leaves it", () => {
    const old = assessHealth(health({ series: series(9, 4) }), NOW, true);
    expect(old.status).toBe("stale");
    expect(old.reasons).toEqual(["data_stale"]);
    expect(assessHealth(health({ forecast: { issuedAt: daysAgo(3) } }), NOW, true).reasons).toEqual(["forecast_stale"]);
    expect(assessHealth(health({ model: { trainedAt: daysAgo(4) } }), NOW, true).reasons).toEqual(["model_stale"]);
  });

  it("the limit is five days of data, not four", () => {
    expect(assessHealth(health({ series: series(MAX_DATA_AGE_DAYS, MAX_DATA_AGE_DAYS) }), NOW, true).status).toBe("ok");
    expect(assessHealth(health({ series: series(MAX_DATA_AGE_DAYS + 1, 4) }), NOW, true).status).toBe("stale");
  });

  it("does not page the owner for an optional dataset that failed this time, only for a long silence", () => {
    const flaky = health({ datasets: [{ ...failing("weather_forecast"), lastDay: day(1) }] });
    const result = assessHealth(flaky, NOW, true);
    expect(result.status).toBe("ok");
    expect(result.reasons).toEqual(["optional_dataset_error"]);
    const silent = health({ datasets: [{ ...failing("weather_forecast"), lastDay: day(12) }] });
    expect(assessHealth(silent, NOW, true)).toMatchObject({ status: "stale", reasons: ["optional_dataset_stale"] });
    const oni = health({ datasets: [{ ...failing("oni"), lastDay: day(80) }] });
    expect(assessHealth(oni, NOW, true).status).toBe("ok"); // the ONI is monthly and about 75 days late
  });

  it("counts calendar days in Bogotá, like the badge: issued at 06:30 on day D is 3 days old on D+3 from midnight", () => {
    // Bogotá is UTC-5: 2026-11-12T11:30Z is 06:30 on the 12th; 2026-11-15T05:30Z is 00:30 on the 15th.
    const edge = health({ forecast: { issuedAt: "2026-11-12T11:30:00Z" } });
    expect(assessHealth(edge, new Date("2026-11-15T05:30:00Z"), true).reasons).toEqual(["forecast_stale"]);
    expect(assessHealth(edge, new Date("2026-11-14T23:00:00Z"), true).reasons).toEqual([]);
  });

  it("degraded wins over stale and lists both reasons", () => {
    const both = assessHealth(health({ datasets: [failing("xm_price")], forecast: { issuedAt: daysAgo(5) } }), NOW, true);
    expect(both.status).toBe("degraded");
    expect(both.reasons).toEqual(["dataset_error", "forecast_stale"]);
  });

  it("reports an unknown age as null instead of guessing", () => {
    expect(assessHealth(health({ series: [] }), NOW, true).ages.dataDays).toBeNull();
  });
});

describe("failureReason", () => {
  it.each([
    ["ConnectTimeout: timed out", "upstream_unreachable"],
    ["XMTransientError: status 503", "upstream_unreachable"],
    ["ReadError: ", "upstream_unreachable"],
    ["HTTPStatusError: Server error '503 Service Unavailable' for url", "upstream_unreachable"],
    ["BatchValidationError: series missing from the batch: demand_kwh", "validation_rejected"],
    ["BatchValidationError: 3 rows dated after 2026-11-14", "validation_rejected"],
    ["KeyError: 'Items'", "error"],
    [null, "error"],
  ])("turns %s into %s", (detail, expected) => {
    expect(failureReason(detail)).toBe(expected);
  });

  it("never lets the original text through", () => {
    expect(failureReason("ConnectTimeout: https://servapibi.xm.com.co/hourly timed out")).not.toContain("xm.com");
  });
});
