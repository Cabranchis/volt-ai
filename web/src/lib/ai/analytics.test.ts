import { describe, expect, it } from "vitest";
import type { SeriesFrame } from "@/lib/data/types";
import { createFixtureRepository } from "@/lib/data/fixtures";
import { comparePeriods, lastTimeAtOrAbove, snapshot, summariseSeries } from "./analytics";

const frame: SeriesFrame = {
  dates: ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"],
  series: {
    price_mean_cop_kwh: [100, 900, 300, 200, 500],
    demand_kwh: [240e6, 250e6, 260e6, null, null],
    reservoir_pct: [0.7, 0.6, 0.5, 0.4, 0.3],
  },
};

describe("summariseSeries", () => {
  it("reports first, last, extremes and mean with their dates and units", () => {
    const s = summariseSeries(frame, "price_mean_cop_kwh");
    expect(s).toMatchObject({
      unit: "COP/kWh",
      days: 5,
      first: { day: "2026-01-01", value: 100 },
      last: { day: "2026-01-05", value: 500 },
      min: { day: "2026-01-01", value: 100 },
      max: { day: "2026-01-02", value: 900 },
      mean: 400,
    });
  });

  it("converts to the display unit so the model never converts kWh itself", () => {
    const s = summariseSeries(frame, "demand_kwh");
    expect(s).toMatchObject({ unit: "GWh/day", last: { day: "2026-01-03", value: 260 }, mean: 250 });
    const r = summariseSeries(frame, "reservoir_pct");
    expect(r).toMatchObject({ unit: "% of capacity", first: { value: 70 } });
  });

  it("restricts to a period and says when there is no data", () => {
    expect(summariseSeries(frame, "price_mean_cop_kwh", "2026-01-03", "2026-01-04")).toMatchObject({ days: 2, mean: 250 });
    expect(summariseSeries(frame, "price_mean_cop_kwh", "2030-01-01")).toEqual({ error: expect.any(String) });
  });

  it("keeps the sample small for long series", () => {
    const long: SeriesFrame = {
      dates: Array.from({ length: 3000 }, (_, i) => new Date(Date.UTC(2018, 0, 1 + i)).toISOString().slice(0, 10)),
      series: { oni: Array.from({ length: 3000 }, (_, i) => i / 1000) },
    };
    const s = summariseSeries(long, "oni");
    expect("sample" in s && s.sample.length).toBeLessThanOrEqual(26);
  });
});

describe("comparePeriods", () => {
  it("compares the means and gives the change from A to B", () => {
    const c = comparePeriods(
      frame,
      "price_mean_cop_kwh",
      { from: "2026-01-01", to: "2026-01-02" },
      { from: "2026-01-04", to: "2026-01-05" },
    );
    expect(c).toMatchObject({ a: { mean: 500, days: 2 }, b: { mean: 350 }, changePercent: -30 });
  });

  it("reports an empty period instead of dividing by nothing", () => {
    expect(comparePeriods(frame, "demand_kwh", { from: "2026-01-04", to: "2026-01-05" }, { from: "2026-01-01", to: "2026-01-02" })).toEqual({
      error: expect.any(String),
    });
  });
});

describe("lastTimeAtOrAbove", () => {
  it("finds the most recent earlier day at or above the latest value", () => {
    const r = lastTimeAtOrAbove(frame, "price_mean_cop_kwh");
    expect(r).toMatchObject({
      latest: { day: "2026-01-05", value: 500 },
      previousDay: { day: "2026-01-02", value: 900, daysAgo: 3 },
    });
  });

  it("uses a threshold given in display units", () => {
    const r = lastTimeAtOrAbove(frame, "demand_kwh", 255);
    expect(r).toMatchObject({ threshold: 255, previousDay: null });
  });

  it("counts days above the threshold in the last year", () => {
    const r = lastTimeAtOrAbove(frame, "price_mean_cop_kwh", 300);
    expect(r).toMatchObject({ daysAboveInLastYear: 3 });
  });
});

describe("snapshot on the real data", () => {
  it("gives every headline figure with a unit, a date and a year-ago comparison", async () => {
    const repo = createFixtureRepository();
    const real = await repo.series(["demand_kwh", "price_mean_cop_kwh", "reservoir_pct", "inflows_pct", "oni", "gen_thermal_kwh", "gen_hydro_kwh", "gen_wind_kwh", "gen_solar_kwh", "gen_cogen_kwh", "gen_other_kwh"]);
    const s = snapshot(real);
    expect(s.demand).toMatchObject({ unit: "GWh/day" });
    expect(Number(s.demand?.["value"])).toBeGreaterThan(150);
    expect(Number(s.demand?.["value"])).toBeLessThan(300);
    expect(s.price).toMatchObject({ unit: "COP/kWh" });
    expect(s.reservoir?.["sameDayLastYear"]).not.toBeNull();
    const mix = s.generationMixPercent!;
    expect(Object.values(mix.now).reduce((a, b) => a + b, 0)).toBeCloseTo(100, 0);
  });
});
