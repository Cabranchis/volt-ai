import { describe, expect, it } from "vitest";
import { horizonSeries, parseTargetMetrics, verdict } from "./model-metrics";

const method = (mase: number, coverage = 0.8) => ({ mape: 3.1, smape: 3.0, mase, coverage_p10_p90: coverage });
const horizon = (a: number, b: number, c: number) => ({
  model: { mase: a, coverage_p10_p90: 0.8 },
  seasonal_naive: { mase: b, coverage_p10_p90: 0.7 },
  ets: { mase: c, coverage_p10_p90: 0.75 },
});
const paired = (reduction: number, won: number) => ({
  mase_model: 1,
  mase_baseline: 1 + reduction / 100,
  mase_reduction_pct: reduction,
  origins_won: won,
  origins: 24,
  wilcoxon_p: 0.01,
});

const target = {
  horizon: 3,
  n_origins: 24,
  first_origin: "2024-01-01",
  last_origin: "2026-09-01",
  nominal_coverage: 0.8,
  overall: { model: method(0.8), seasonal_naive: method(1.2), ets: method(0.9) },
  by_horizon: { "2": horizon(0.7, 1.1, 0.8), "1": horizon(0.6, 1.0, 0.7), "3": horizon(0.9, 1.3, 1.0) },
  paired: { seasonal_naive: paired(33, 22), ets: paired(-5, 9) },
  coverage: { raw: 0.62, calibrated: 0.79 },
};

describe("parseTargetMetrics", () => {
  it("reads the backtest structure the pipeline writes", () => {
    const parsed = parseTargetMetrics({ targets: { demand_kwh: target } }, "demand_kwh");
    expect(parsed?.n_origins).toBe(24);
    expect(parsed?.coverage.calibrated).toBe(0.79);
  });

  it("returns null, not wrong numbers, when a target or a field is missing", () => {
    expect(parseTargetMetrics({}, "demand_kwh")).toBeNull();
    expect(parseTargetMetrics({ targets: {} }, "demand_kwh")).toBeNull();
    expect(parseTargetMetrics({ targets: { demand_kwh: { ...target, overall: undefined } } }, "demand_kwh")).toBeNull();
  });

  it("accepts a run where calibration did not have enough history", () => {
    const parsed = parseTargetMetrics({ targets: { x: { ...target, coverage: { raw: 0.7, calibrated: null } } } }, "x");
    expect(parsed?.coverage.calibrated).toBeNull();
  });
});

describe("verdict", () => {
  it("says the model wins when its error is lower", () => {
    expect(verdict(target.paired.seasonal_naive)).toEqual({ beats: true, pct: 33, won: 22, total: 24 });
  });

  it("says the model does not win when its error is higher, with the size of the gap", () => {
    expect(verdict(target.paired.ets)).toEqual({ beats: false, pct: 5, won: 9, total: 24 });
  });

  it("treats a tie as not beating the baseline", () => {
    expect(verdict(paired(0, 12)).beats).toBe(false);
  });
});

describe("horizonSeries", () => {
  it("orders the horizons numerically, not as text", () => {
    const parsed = parseTargetMetrics({ targets: { x: target } }, "x");
    const series = horizonSeries(parsed!);
    expect(series.days).toEqual([1, 2, 3]);
    expect(series.model).toEqual([0.6, 0.7, 0.9]);
    expect(series.seasonalNaive).toEqual([1.0, 1.1, 1.3]);
  });
});
