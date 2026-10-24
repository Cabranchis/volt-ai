import { describe, expect, it } from "vitest";
import { createFixtureRepository } from "./data/fixtures";
import { pivotRows, sliceFrame } from "./data/shape";
import type { SeriesFrame } from "./data/types";
import { dayIndex, kpi, lastDayOf, meanOfFirst, MIX_ORDER, mixShares, monthlyMix, oniPhase, valueOn, weekdayProfile } from "./insights";

const frame: SeriesFrame = {
  dates: ["2026-10-01", "2026-10-02", "2026-10-08", "2026-10-09"],
  series: {
    demand_kwh: [100, 110, 120, null],
    gen_thermal_kwh: [30, 30, 30, 30],
    gen_hydro_kwh: [60, 60, 60, 60],
    gen_wind_kwh: [1, 1, 1, 1],
    gen_solar_kwh: [5, 5, 5, 5],
    gen_cogen_kwh: [3, 3, 3, 3],
    gen_other_kwh: [1, 1, 1, null],
  },
};

describe("series helpers", () => {
  it("finds days by binary search", () => {
    expect(dayIndex(frame, "2026-10-08")).toBe(2);
    expect(dayIndex(frame, "2026-10-05")).toBe(-1);
    expect(valueOn(frame, "demand_kwh", "2026-10-02")).toBe(110);
  });

  it("ignores trailing nulls when finding the last day", () => {
    expect(lastDayOf(frame, "demand_kwh")).toBe("2026-10-08");
    expect(lastDayOf(frame, "missing")).toBeNull();
  });

  it("computes a weekly delta only when the earlier day exists", () => {
    expect(kpi(frame, "demand_kwh")).toEqual({ day: "2026-10-08", value: 120, previous: 100, delta: 20 });
    expect(kpi(frame, "demand_kwh", 3)?.previous).toBeNull();
  });
});

describe("generation mix", () => {
  it("shares add up to one", () => {
    const shares = mixShares(frame, "2026-10-01");
    expect(shares).not.toBeNull();
    expect(MIX_ORDER.reduce((sum, key) => sum + (shares?.[key] ?? 0), 0)).toBeCloseTo(1, 10);
    expect(shares?.hydro).toBeCloseTo(0.6, 10);
  });

  it("returns null when any source is missing for the day", () => {
    expect(mixShares(frame, "2026-10-09")).toBeNull();
  });

  it("builds monthly shares that each add up to one", () => {
    const { months, shares } = monthlyMix(frame);
    expect(months).toEqual(["2026-10"]);
    expect(MIX_ORDER.reduce((sum, key) => sum + shares[key][0]!, 0)).toBeCloseTo(1, 10);
  });
});

describe("El Niño phase", () => {
  it.each([
    [2.16, "strongNino"],
    [1.5, "strongNino"],
    [0.5, "nino"],
    [0.49, "neutral"],
    [-0.49, "neutral"],
    [-0.5, "nina"],
  ] as const)("ONI %s is %s", (value, phase) => {
    expect(oniPhase(value)).toBe(phase);
  });
});

describe("misc", () => {
  it("averages the first n forecast medians", () => {
    expect(meanOfFirst([{ p50: 1 }, { p50: 3 }, { p50: 100 }], 2)).toBe(2);
    expect(meanOfFirst([], 7)).toBeNull();
  });

  it("builds a Monday-first weekday profile from calendar dates", () => {
    const week: SeriesFrame = {
      dates: ["2026-10-19", "2026-10-20", "2026-10-25"], // Mon, Tue, Sun
      series: { x: [10, 20, 30] },
    };
    const profile = weekdayProfile(week, "x", 10);
    expect(profile[0]?.mean).toBe(10);
    expect(profile[1]?.mean).toBe(20);
    expect(profile[6]?.mean).toBe(30);
    expect(profile[2]?.mean).toBe(0);
  });

  it("pivots long rows and slices by range", () => {
    const pivoted = pivotRows(
      [
        { series: "a", day: "2026-01-01", value: 1 },
        { series: "b", day: "2026-01-02", value: 2 },
      ],
      ["a", "b"],
    );
    expect(pivoted.series.a).toEqual([1, null]);
    expect(pivoted.series.b).toEqual([null, 2]);
    expect(sliceFrame(pivoted, ["b"], { from: "2026-01-02" }).dates).toEqual(["2026-01-02"]);
  });
});

describe("fixture repository (contract with the pipeline's export)", () => {
  it("loads and validates every fixture file", async () => {
    const repo = createFixtureRepository();
    const health = await repo.health();
    expect(health.source).toBe("fixtures");
    const latest = await repo.latest(["demand_kwh", "price_mean_cop_kwh", "reservoir_pct", "oni"]);
    expect(latest.demand_kwh?.value).toBeGreaterThan(100e6);
    expect(latest.reservoir_pct?.value).toBeLessThanOrEqual(1);
  });

  it("serves the real series from 2018", async () => {
    const repo = createFixtureRepository();
    const frame = await repo.series(["demand_kwh"], { from: "2018-01-01", to: "2018-01-31" });
    expect(frame.dates[0]).toBe("2018-01-01");
    expect(frame.series.demand_kwh?.filter((v) => v !== null).length).toBeGreaterThan(28);
  });
});
