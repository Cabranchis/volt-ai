import { describe, expect, it } from "vitest";
import { checkInputs, parseAmount, percentile, seededRandom, simulateCost, windowDays } from "./cost";
import type { ForecastPoint } from "./data/types";
import { exceedance } from "./spikes";

const point = (day: string, horizon: number, p10: number, p50: number, p90: number): ForecastPoint => ({
  day,
  horizon,
  p10,
  p50,
  p90,
  drivers: null,
});

const week: ForecastPoint[] = [
  point("2026-10-26", 3, 500, 600, 750),
  point("2026-10-27", 4, 480, 620, 800),
  point("2026-10-28", 5, 470, 640, 850),
  point("2026-10-29", 6, 460, 650, 900),
];

describe("windowDays", () => {
  it("starts on the given day and stops at the requested length", () => {
    expect(windowDays(week, "2026-10-27", 2).map((p) => p.day)).toEqual(["2026-10-27", "2026-10-28"]);
  });

  it("returns what exists when fewer days are available than requested", () => {
    expect(windowDays(week, "2026-10-28", 10)).toHaveLength(2);
    expect(windowDays(week, "2026-11-30", 3)).toEqual([]);
  });
});

describe("seededRandom and percentile", () => {
  it("repeats for the same seed and differs for another", () => {
    const a = seededRandom(1);
    const b = seededRandom(1);
    expect([a(), a(), a()]).toEqual([b(), b(), b()]);
    expect(seededRandom(2)()).not.toBe(seededRandom(1)());
  });

  it("interpolates between sorted values", () => {
    const sorted = Float64Array.from([10, 20, 30, 40]);
    expect(percentile(sorted, 0)).toBe(10);
    expect(percentile(sorted, 1)).toBe(40);
    expect(percentile(sorted, 0.5)).toBe(25);
  });
});

describe("parseAmount", () => {
  it("reads whole numbers and one decimal mark, a dot or a comma", () => {
    expect(parseAmount("250")).toBe(250);
    expect(parseAmount(" 12.5 ")).toBe(12.5);
    expect(parseAmount("1,5")).toBe(1.5);
    expect(parseAmount("0,125")).toBe(0.125);
  });

  it("rejects what could be a thousands separator instead of guessing", () => {
    expect(parseAmount("1.000")).toBeNaN();
    expect(parseAmount("1,000")).toBeNaN();
    expect(parseAmount("12.345")).toBeNaN();
    expect(parseAmount("1.000.000")).toBeNaN();
  });

  it("rejects empty and unreadable text", () => {
    for (const text of ["", " ", "abc", "-5", "1e3", "5,", ".5"]) expect(parseAmount(text)).toBeNaN();
  });
});

describe("checkInputs", () => {
  it("accepts a normal request and names the first problem otherwise", () => {
    expect(checkInputs(100, 7, null)).toBeNull();
    expect(checkInputs(100, 7, 450)).toBeNull();
    expect(checkInputs(0, 7, null)).toBe("volume");
    expect(checkInputs(-5, 7, null)).toBe("volume");
    expect(checkInputs(Number.NaN, 7, null)).toBe("volume");
    expect(checkInputs(100, 0, null)).toBe("days");
    expect(checkInputs(100, 2.5, null)).toBe("days");
    expect(checkInputs(100, 7, -1)).toBe("contract");
  });
});

describe("simulateCost", () => {
  it("with fully correlated days, the median cost is the volume times each day's median price", () => {
    const result = simulateCost({ points: week, mwhPerDay: 100, rho: 1 });
    const exact = (100 / 1000) * (600 + 620 + 640 + 650);
    expect(result?.cost.p50).toBeGreaterThan(exact * 0.99);
    expect(result?.cost.p50).toBeLessThan(exact * 1.01);
  });

  it("with fully correlated days, the P10 and P90 of the cost are the sums of the daily P10 and P90", () => {
    const result = simulateCost({ points: week, mwhPerDay: 100, rho: 1, draws: 20000 });
    const p10 = (100 / 1000) * week.reduce((s, p) => s + p.p10, 0);
    const p90 = (100 / 1000) * week.reduce((s, p) => s + p.p90, 0);
    expect(result?.cost.p10).toBeGreaterThan(p10 * 0.97);
    expect(result?.cost.p10).toBeLessThan(p10 * 1.03);
    expect(result?.cost.p90).toBeGreaterThan(p90 * 0.97);
    expect(result?.cost.p90).toBeLessThan(p90 * 1.03);
  });

  it("makes the range narrower when days are less correlated", () => {
    const wide = simulateCost({ points: week, mwhPerDay: 100, rho: 1 });
    const narrow = simulateCost({ points: week, mwhPerDay: 100, rho: 0 });
    expect((narrow?.cost.p90 ?? 0) - (narrow?.cost.p10 ?? 0)).toBeLessThan((wide?.cost.p90 ?? 0) - (wide?.cost.p10 ?? 0));
  });

  it("for one day equals the log-normal of that day, whatever rho is", () => {
    const one = [point("2026-10-27", 4, 480, 620, 800)];
    const result = simulateCost({ points: one, mwhPerDay: 50, rho: 0.7, draws: 20000, contractCopKwh: 700 });
    const expected = 1 - (exceedance(one[0] as ForecastPoint, 700) as number);
    // P(spot cost > contract cost) = P(price > 700).
    expect(result?.contract?.probSpotHigher).toBeGreaterThan((1 - expected) - 0.02);
    expect(result?.contract?.probSpotHigher).toBeLessThan((1 - expected) + 0.02);
  });

  it("keeps the median and the log-spread of an asymmetric band, not its stored P10 and P90", () => {
    // 400 / 600 / 1200: the log-spread is symmetric around the median, so the simulated P90 is 600 * sqrt(3).
    const skewed = [point("2026-10-27", 4, 400, 600, 1200)];
    const result = simulateCost({ points: skewed, mwhPerDay: 1000, rho: 0.7, draws: 40000 });
    expect(result?.cost.p50).toBeGreaterThan(600 * 0.98);
    expect(result?.cost.p50).toBeLessThan(600 * 1.02);
    expect(result?.cost.p90).toBeGreaterThan(600 * Math.sqrt(3) * 0.97);
    expect(result?.cost.p90).toBeLessThan(600 * Math.sqrt(3) * 1.03);
    // The per-day table shows the stored band as it is.
    expect(result?.days[0]?.costP90).toBeCloseTo(1200, 6);
  });

  it("repeats exactly for the same seed", () => {
    const a = simulateCost({ points: week, mwhPerDay: 100, rho: 0.7 });
    const b = simulateCost({ points: week, mwhPerDay: 100, rho: 0.7 });
    expect(a).toEqual(b);
  });

  it("reports the volume-weighted mean price and the total volume", () => {
    const result = simulateCost({ points: week, mwhPerDay: 100, rho: 1 });
    expect(result?.totalMwh).toBe(400);
    const meanMedian = (600 + 620 + 640 + 650) / 4;
    expect(result?.meanPrice.p50).toBeGreaterThan(meanMedian * 0.99);
    expect(result?.meanPrice.p50).toBeLessThan(meanMedian * 1.01);
  });

  it("scales the cost with the volume", () => {
    const small = simulateCost({ points: week, mwhPerDay: 100, rho: 0.7 });
    const large = simulateCost({ points: week, mwhPerDay: 300, rho: 0.7 });
    expect((large?.cost.p50 ?? 0) / (small?.cost.p50 ?? 1)).toBeCloseTo(3, 6);
  });

  it("compares with a contract: a contract far above the forecast is never beaten by the spot market", () => {
    const result = simulateCost({ points: week, mwhPerDay: 100, rho: 0.7, contractCopKwh: 3000 });
    expect(result?.contract?.probSpotHigher).toBe(0);
    expect(result?.contract?.expectedGap).toBeLessThan(0);
    expect(result?.contract?.cost).toBeCloseTo((400 * 3000) / 1000, 6);
  });

  it("drops days whose band cannot be read and says how many", () => {
    const broken = [...week, point("2026-10-30", 7, 0, 600, 700), point("2026-10-31", 8, 700, 600, 500)];
    const result = simulateCost({ points: broken, mwhPerDay: 100, rho: 0.7 });
    expect(result?.skipped).toBe(2);
    expect(result?.days).toHaveLength(4);
  });

  it("gives nothing when there is nothing to compute", () => {
    expect(simulateCost({ points: [], mwhPerDay: 100, rho: 0.7 })).toBeNull();
    expect(simulateCost({ points: week, mwhPerDay: 0, rho: 0.7 })).toBeNull();
    expect(simulateCost({ points: week, mwhPerDay: 100, rho: 1.5 })).toBeNull();
  });
});
