import { describe, expect, it } from "vitest";
import { assembleForecast } from "./forecast-data";
import { lastNonNullIndex, rollingMean, spreadMonthly } from "./series-utils";

const history = {
  dates: ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05"],
  values: [10, 11, 12, null, null] as (number | null)[],
};

describe("assembleForecast", () => {
  const forecast = [
    { day: "2026-10-04", p10: 11, p50: 13, p90: 15 },
    { day: "2026-10-05", p10: 10, p50: 13.5, p90: 17 },
  ];

  it("starts the forecast the day after the last observed value, ignoring trailing nulls", () => {
    const a = assembleForecast(history, forecast, null)!;
    expect(a.lastObservedDate).toBe("2026-10-03");
    expect(a.dates).toEqual(["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05"]);
    expect(a.observed).toEqual([10, 11, 12, null, null]);
  });

  it("opens the median and the band from the last real value, so the line does not jump", () => {
    const a = assembleForecast(history, forecast, null)!;
    expect(a.median).toEqual([null, null, 12, 13, 13.5]);
    expect(a.lower).toEqual([null, null, 12, 11, 10]);
    expect(a.width).toEqual([null, null, 0, 4, 7]);
  });

  it("keeps lower + width equal to P90", () => {
    const a = assembleForecast(history, forecast, null)!;
    const upper = a.lower.map((l, i) => (l === null ? null : l + (a.width[i] ?? 0)));
    expect(upper.slice(3)).toEqual([15, 17]);
  });

  it("drops forecast days that are not after the last observation", () => {
    const stale = [{ day: "2026-10-02", p10: 1, p50: 2, p90: 3 }, ...forecast];
    expect(assembleForecast(history, stale, null)!.dates).toHaveLength(5);
  });

  it("limits how much history is shown", () => {
    const a = assembleForecast(history, forecast, 2)!;
    expect(a.dates).toEqual(["2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05"]);
    expect(a.lastObservedIndex).toBe(1);
  });

  it("returns null when nothing was observed", () => {
    expect(assembleForecast({ dates: ["2026-10-01"], values: [null] }, forecast, null)).toBeNull();
  });

  it("works without a forecast", () => {
    const a = assembleForecast(history, [], null)!;
    expect(a.median.every((v) => v === null)).toBe(true);
  });
});

describe("series utilities", () => {
  it("computes a trailing mean over the available points", () => {
    expect(rollingMean([1, 2, 3, 4], 2)).toEqual([1, 1.5, 2.5, 3.5]);
  });

  it("skips nulls in the trailing mean", () => {
    expect(rollingMean([2, null, 4], 3)).toEqual([2, 2, 3]);
  });

  it("spreads a monthly value over its own month only", () => {
    const dates = ["2026-08-01", "2026-08-31", "2026-09-01", "2026-10-15"];
    const monthly = [2.16, null, null, null];
    // September and October have not been published, so they stay empty.
    expect(spreadMonthly(dates, monthly)).toEqual([2.16, 2.16, null, null]);
  });

  it("finds the last non-null index", () => {
    expect(lastNonNullIndex([1, null, 3, null])).toBe(2);
    expect(lastNonNullIndex([null])).toBe(-1);
  });
});
