import { describe, expect, it } from "vitest";
import { exceedance, normalCdf, peakDay, recentMean, spikeOutlook } from "./spikes";

const point = (day: string, horizon: number, p10: number, p50: number, p90: number) => ({
  day,
  horizon,
  p10,
  p50,
  p90,
  drivers: null,
});

describe("normalCdf", () => {
  it("matches known values", () => {
    expect(normalCdf(0)).toBeCloseTo(0.5, 6);
    expect(normalCdf(1.2815515655)).toBeCloseTo(0.9, 5);
    expect(normalCdf(-1.96)).toBeCloseTo(0.025, 3);
  });
});

describe("exceedance", () => {
  it("is one half at the median", () => {
    expect(exceedance(point("d", 1, 200, 300, 450), 300)).toBeCloseTo(0.5, 6);
  });
  it("reproduces the P90 and P10 of the log-normal it is built from", () => {
    const p = point("d", 1, 200, 300, 450);
    // P10 and P90 are symmetric around the median in logs only when the band is, so build one
    const sym = point("d", 1, 300 / 1.5, 300, 300 * 1.5);
    expect(exceedance(sym, 450)).toBeCloseTo(0.1, 4);
    expect(exceedance(sym, 200)).toBeCloseTo(0.9, 4);
    expect(exceedance(p, 1e6)).toBeLessThan(1e-6);
  });
  it("rejects bands that cannot be read as a distribution", () => {
    expect(exceedance(point("d", 1, 0, 300, 450), 300)).toBeNull();
    expect(exceedance(point("d", 1, 400, 300, 400), 300)).toBeNull();
    expect(exceedance(point("d", 1, 200, 300, 450), 0)).toBeNull();
  });
});

describe("recentMean", () => {
  it("needs at least twenty settled days", () => {
    expect(recentMean(new Array(19).fill(100))).toBeNull();
    expect(recentMean(new Array(20).fill(100))).toBe(100);
  });
  it("uses only the last thirty and skips gaps", () => {
    const values = [...new Array(10).fill(1000), ...new Array(30).fill(null), ...new Array(30).fill(200)];
    expect(recentMean(values)).toBe(200);
  });
});

describe("spikeOutlook", () => {
  const history = new Array(40).fill(250);
  it("returns null without enough history", () => {
    expect(spikeOutlook([point("d", 1, 200, 300, 450)], [250])).toBeNull();
  });
  it("gives a probability per day for both events and finds the peak", () => {
    const outlook = spikeOutlook(
      [point("2026-10-27", 1, 200, 260, 330), point("2026-10-28", 2, 300, 520, 800)],
      history,
    );
    expect(outlook?.baseline).toBe(250);
    expect(outlook?.days).toHaveLength(2);
    const [first, second] = outlook?.days ?? [];
    expect(first?.aboveLevel).toBeLessThan(0.05);
    expect(second?.aboveLevel).toBeGreaterThan(0.5);
    expect(second?.rise).toBeGreaterThan(first?.rise ?? 1);
    expect(outlook && peakDay(outlook, "aboveLevel").horizon).toBe(2);
  });
});
