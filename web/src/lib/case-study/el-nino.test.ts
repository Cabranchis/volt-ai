import { describe, expect, it } from "vitest";
import { buildCaseSeries, CASE_STUDY, insideBand, lastFullMonth, monthProfile, REGIME_KEYS } from "./el-nino";

describe("buildCaseSeries", () => {
  const point = {
    origin: "2024-01-03",
    scores: { model: 1, ets: 2, naive: 3, coverage: 1 },
    history: [
      { day: "2024-01-02", y: 100 },
      { day: "2024-01-03", y: 110 },
    ],
    rows: [
      { day: "2024-01-04", y: 120, p10: 80, p50: 105, p90: 150, ets: 108 },
      { day: "2024-01-05", y: null, p10: 70, p50: 104, p90: 160, ets: 108 },
    ],
  };
  const s = buildCaseSeries(point);

  it("puts history and forecast days on one axis", () => {
    expect(s.dates).toEqual(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]);
    expect(s.originIndex).toBe(1);
    expect(s.observed).toEqual([100, 110, 120, null]);
  });

  it("opens the median, the band and ETS from the last known price", () => {
    expect(s.median).toEqual([null, 110, 105, 104]);
    expect(s.lower).toEqual([null, 110, 80, 70]);
    expect(s.width).toEqual([null, 0, 70, 90]);
    expect(s.ets).toEqual([null, 110, 108, 108]);
  });

  it("counts the days inside the band from the production coverage", () => {
    expect(insideBand(point)).toEqual({ inside: 1, total: 1 });
  });
});

describe("monthProfile", () => {
  const frame = {
    dates: ["2026-06-01", "2026-08-01", "2026-10-01", "2026-10-02", "2026-10-03"],
    series: {
      price_mean_cop_kwh: [1, 1, 600, 700, null],
      reservoir_pct: [0.8, 0.8, 0.77, 0.75, null],
      inflows_pct: [1, 1, 0.5, 0.7, null],
      gen_thermal_kwh: [1, 1, 30, null, 50],
      gen_total_kwh: [10, 10, 100, 100, null],
      oni: [1.1, 2.2, null, null, null],
    },
  };
  it("summarises one month, pairing thermal and total on the same days", () => {
    const m = monthProfile(frame, "2026-10");
    expect(m.price).toBe(650);
    expect(m.reservoirMin).toBeCloseTo(75);
    expect(m.inflows).toBeCloseTo(60);
    expect(m.thermal).toBeCloseTo(30);
  });
  it("uses the ONI already published at the end of the month", () => {
    // 2026-08-01 + 75 days is 2026-10-15: on 2026-10-03 only the June value is published.
    expect(monthProfile(frame, "2026-10").oni).toBe(1.1);
    expect(monthProfile({ ...frame, dates: [...frame.dates.slice(0, 4), "2026-10-20"] }, "2026-10").oni).toBe(2.2);
  });
  it("returns nulls for a month with no data", () => {
    expect(monthProfile(frame, "2020-01")).toEqual({ price: null, reservoirMin: null, inflows: null, thermal: null, oni: null });
  });
});

describe("lastFullMonth", () => {
  const days = (month: string, n: number) => Array.from({ length: n }, (_, i) => `${month}-${String(i + 1).padStart(2, "0")}`);
  it("skips a month that has only a few days of price", () => {
    const dates = [...days("2026-10", 30), ...days("2026-11", 1)];
    expect(lastFullMonth({ dates, series: { price_mean_cop_kwh: dates.map(() => 500) } })).toBe("2026-10");
  });
});

describe("packaged data", () => {
  it("has every regime and four cases with 14 forecast days", () => {
    for (const key of REGIME_KEYS) expect(CASE_STUDY.regimes[key].origins).toBeGreaterThan(0);
    expect(CASE_STUDY.cases).toHaveLength(4);
    for (const c of CASE_STUDY.cases) expect(c.rows).toHaveLength(14);
  });
});
