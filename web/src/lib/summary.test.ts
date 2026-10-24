import { describe, expect, it } from "vitest";
import type { Kpi, MixShares } from "./insights";
import { buildSummary, describeForecast, describeSeries, type SummaryInput } from "./summary";

const k = (day: string, value: number, previous: number | null): Kpi => ({
  day,
  value,
  previous,
  delta: previous === null ? null : value - previous,
});
const mix = (thermal: number): MixShares => ({ thermal, hydro: 1 - thermal - 0.1, wind: 0.01, solar: 0.08, cogen: 0.01, other: 0 });

const base: SummaryInput = {
  locale: "en",
  demand: k("2026-10-21", 245_325_064.64, 245_000_000),
  price: k("2026-10-21", 488, 530),
  reservoir: k("2026-10-23", 0.765, 0.76),
  oni: k("2026-08-01", 2.16, null),
  mix: mix(0.388),
  mixYearAgo: mix(0.1),
  demandNextWeek: 243_000_000,
  priceNextWeek: 520,
};

describe("buildSummary", () => {
  it("states each figure with its date and unit", () => {
    const text = buildSummary(base);
    expect(text).toContain("245.3 GWh");
    expect(text).toContain("488 COP/kWh");
    expect(text).toContain("76.5 %");
    expect(text).toContain("strong El Niño");
    expect(text).toContain("39 %");
    expect(text).toContain("10 % a year ago");
  });

  it("says a flat week is flat instead of inventing a direction", () => {
    expect(buildSummary(base)).toContain("essentially unchanged");
  });

  it("describes a real week-on-week move with its sign in words", () => {
    const up = buildSummary({ ...base, demand: k("2026-10-21", 260e6, 240e6) });
    expect(up).toContain("above the same day a week earlier");
    const down = buildSummary({ ...base, demand: k("2026-10-21", 220e6, 240e6) });
    expect(down).toContain("below the same day a week earlier");
  });

  it("skips sentences whose figures are missing, never filling in a number", () => {
    const text = buildSummary({ ...base, price: null, priceNextWeek: null, mix: null, oni: null });
    expect(text).not.toContain("COP");
    expect(text).not.toContain("Thermal");
    expect(text).not.toContain("ONI");
  });

  it("returns an empty string with no data at all", () => {
    expect(
      buildSummary({ locale: "es", demand: null, price: null, reservoir: null, oni: null, mix: null, mixYearAgo: null, demandNextWeek: null, priceNextWeek: null }),
    ).toBe("");
  });

  it("is written in Spanish for Spanish readers, with Colombian number format", () => {
    const text = buildSummary({ ...base, locale: "es" });
    expect(text).toContain("245,3 GWh");
    expect(text).toContain("Los embalses están al 76,5 %");
    expect(text).toContain("El Niño fuerte");
  });
});

describe("describeForecast / describeSeries", () => {
  it("summarises range and mean of the median", () => {
    const text = describeForecast({
      locale: "en",
      points: [
        { p10: 200e6, p50: 240e6, p90: 260e6 },
        { p10: 210e6, p50: 250e6, p90: 270e6 },
      ],
      scale: 1e6,
      decimals: 0,
      unit: "GWh/day",
    });
    expect(text).toContain("Next 2 days");
    expect(text).toContain("240 to 250");
    expect(text).toContain("mean 245");
    expect(text).toContain("200 to 270");
  });

  it("is empty for no points", () => {
    expect(describeForecast({ locale: "en", points: [], scale: 1, decimals: 0, unit: "" })).toBe("");
  });

  it("reports first, last and extremes of a series", () => {
    const text = describeSeries({
      locale: "en",
      label: "Reservoir",
      dates: ["2026-01-01", "2026-01-02", "2026-01-03"],
      values: [0.7, 0.3, 0.5],
      scale: 0.01,
      decimals: 0,
      unit: "%",
    });
    expect(text).toContain("from 70 % on Jan 1, 2026 to 50 % on Jan 3, 2026");
    expect(text).toContain("Low 30 % on Jan 2, 2026");
    expect(text).toContain("high 70 % on Jan 1, 2026");
  });
});
