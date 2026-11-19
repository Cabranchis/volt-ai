import { describe, expect, it } from "vitest";
import { bucketErrors, horizonSeries, parseTargetMetrics, verdict } from "./model-metrics";

const method = (mase: number, coverage = 0.8) => ({ mape: 3.1, smape: 3.0, mase, coverage_p10_p90: coverage });
const horizon = (a: number, b: number, c: number) => ({
  model: { mase: a, coverage_p10_p90: 0.8 },
  seasonal_naive: { mase: b, coverage_p10_p90: 0.7 },
  ets: { mase: c, coverage_p10_p90: 0.75 },
});
const paired = (reduction: number, won: number, ci?: [number, number] | null) => ({
  mase_model: 1,
  mase_baseline: 1 + reduction / 100,
  mase_reduction_pct: reduction,
  origins_won: won,
  origins: 24,
  wilcoxon_p: 0.01,
  ...(ci === undefined ? {} : { mase_diff_ci95: ci }),
});

const target = {
  horizon: 3,
  n_origins: 24,
  first_origin: "2024-01-01",
  last_origin: "2026-09-01",
  nominal_coverage: 0.8,
  overall: { model: method(0.8), seasonal_naive: method(1.2), ets: method(0.9) },
  by_horizon: { "2": horizon(0.7, 1.1, 0.8), "1": horizon(0.6, 1.0, 0.7), "3": horizon(0.9, 1.3, 1.0) },
  paired: { seasonal_naive: paired(33, 22, [-0.5, -0.2]), ets: paired(-5, 9, [0.1, 0.4]) },
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
  it("says the model wins only when the interval of the difference is entirely below zero", () => {
    expect(verdict(target.paired.seasonal_naive)).toEqual({
      kind: "beats",
      beats: true,
      lower: true,
      pct: 33,
      won: 22,
      total: 24,
    });
  });

  it("says the model loses only when the interval is entirely above zero, with the size of the gap", () => {
    expect(verdict(target.paired.ets)).toEqual({ kind: "loses", beats: false, lower: false, pct: 5, won: 9, total: 24 });
  });

  it("says it cannot tell when the interval includes zero, even if the mean error is lower", () => {
    expect(verdict(paired(14, 36, [-0.49, 0.06]))).toMatchObject({ kind: "ties", beats: false, lower: true, pct: 14 });
    expect(verdict(paired(-3, 10, [-0.1, 0.2]))).toMatchObject({ kind: "ties", lower: false });
  });

  it("does not claim a win without an interval (too few origins, or an older run)", () => {
    expect(verdict(paired(30, 20)).kind).toBe("ties");
    expect(verdict(paired(30, 20, null)).kind).toBe("ties");
  });

  it("treats a tie as not beating the baseline", () => {
    expect(verdict(paired(0, 12, [-0.1, 0.1])).beats).toBe(false);
  });
});

describe("the last price reference", () => {
  const withLast = {
    ...target,
    overall: { ...target.overall, last_price: { mape: 30.1, smape: 28, mase: 1.7 } },
    by_horizon: { "1": { ...horizon(0.6, 1.0, 0.7), last_price: { mase: 0.9 } } },
    by_bucket: {
      "1-3": { model: { mape: 10 }, seasonal_naive: { mape: 30 }, ets: { mape: 15 }, last_price: { mape: 16 } },
    },
    paired: { ...target.paired, last_price: paired(8, 14, [-0.2, 0.1]) },
  };

  it("is read when the run has it, with no band", () => {
    const parsed = parseTargetMetrics({ targets: { price_mean_cop_kwh: withLast } }, "price_mean_cop_kwh");
    expect(parsed?.overall.last_price).toEqual({ mape: 30.1, smape: 28, mase: 1.7 });
    expect(parsed && verdict(parsed.paired.last_price!).kind).toBe("ties");
    expect(parsed && bucketErrors(parsed)[0]?.lastPrice).toBe(16);
    expect(parsed && horizonSeries(parsed).lastPrice).toEqual([0.9]);
  });

  it("is absent, not an error, for a run without it (the demand, or an older run)", () => {
    const parsed = parseTargetMetrics({ targets: { demand_kwh: target } }, "demand_kwh");
    expect(parsed?.overall.last_price).toBeUndefined();
    expect(parsed?.paired.last_price).toBeUndefined();
    expect(parsed && horizonSeries(parsed).lastPrice).toEqual([null, null, null]);
  });

  it("does not make the whole run unreadable when only this part is malformed", () => {
    const broken = {
      ...withLast,
      overall: { ...withLast.overall, last_price: { mape: "x" } },
      paired: { ...target.paired, last_price: { nope: 1 } },
    };
    const parsed = parseTargetMetrics({ targets: { price_mean_cop_kwh: broken } }, "price_mean_cop_kwh");
    expect(parsed).not.toBeNull();
    expect(parsed?.overall.last_price).toBeUndefined();
    expect(parsed?.paired.last_price).toBeUndefined();
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

describe("bucketErrors", () => {
  it("lists the mean error by horizon bucket, shortest first", () => {
    const pct = (mape: number) => ({ mape });
    const bucket = (m: number, n: number, e: number) => ({ model: pct(m), seasonal_naive: pct(n), ets: pct(e) });
    const withBuckets = {
      ...target,
      by_bucket: { "8-14": bucket(35, 41, 34), "1-3": bucket(10, 30, 15), "4-7": bucket(25, 40, 28) },
    };
    const parsed = parseTargetMetrics({ targets: { price_mean_cop_kwh: withBuckets } }, "price_mean_cop_kwh");
    expect(parsed && bucketErrors(parsed).map((b) => b.label)).toEqual(["1-3", "4-7", "8-14"]);
    expect(parsed && bucketErrors(parsed)[0]).toEqual({ label: "1-3", model: 10, seasonalNaive: 30, ets: 15, lastPrice: null });
  });

  it("is empty for a run that stored no buckets", () => {
    const parsed = parseTargetMetrics({ targets: { demand_kwh: target } }, "demand_kwh");
    expect(parsed && bucketErrors(parsed)).toEqual([]);
  });
});
