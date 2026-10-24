import { z } from "zod";

/**
 * Shape of `model_runs.metrics` written by the pipeline's backtest (pipeline/src/voltia/models/backtest.py).
 * Parsed defensively: unknown extra keys are kept out of the way, missing ones make the page say
 * "metrics unavailable" instead of showing wrong numbers.
 */
const method = z.object({
  mape: z.number(),
  smape: z.number(),
  mase: z.number(),
  coverage_p10_p90: z.number(),
});

const paired = z.object({
  mase_model: z.number(),
  mase_baseline: z.number(),
  mase_reduction_pct: z.number(),
  origins_won: z.number(),
  origins: z.number(),
  wilcoxon_p: z.number().nullable(),
});

const horizonMethod = z.object({ mase: z.number(), coverage_p10_p90: z.number() });

export const targetMetricsSchema = z.object({
  horizon: z.number(),
  n_origins: z.number(),
  first_origin: z.string(),
  last_origin: z.string(),
  nominal_coverage: z.number(),
  overall: z.object({ model: method, seasonal_naive: method, ets: method }),
  by_horizon: z.record(
    z.string(),
    z.object({ model: horizonMethod, seasonal_naive: horizonMethod, ets: horizonMethod }),
  ),
  paired: z.object({ seasonal_naive: paired, ets: paired }),
  coverage: z.object({ raw: z.number(), calibrated: z.number().nullable() }),
});
export type TargetMetrics = z.infer<typeof targetMetricsSchema>;

export function parseTargetMetrics(metrics: Record<string, unknown>, target: string): TargetMetrics | null {
  const targets = metrics["targets"];
  if (typeof targets !== "object" || targets === null) return null;
  const parsed = targetMetricsSchema.safeParse((targets as Record<string, unknown>)[target]);
  return parsed.success ? parsed.data : null;
}

export interface Verdict {
  /** True when the model's error is lower than the baseline's. */
  beats: boolean;
  /** Absolute size of the difference in MASE, in percent of the baseline's. */
  pct: number;
  won: number;
  total: number;
}

/** Reads the paired comparison as a plain verdict. A tie counts as "does not beat". */
export function verdict(p: TargetMetrics["paired"]["seasonal_naive"]): Verdict {
  return { beats: p.mase_reduction_pct > 0, pct: Math.abs(p.mase_reduction_pct), won: p.origins_won, total: p.origins };
}

/** MASE by day ahead as three aligned arrays, ordered by horizon. */
export function horizonSeries(metrics: TargetMetrics) {
  const days = Object.keys(metrics.by_horizon)
    .map(Number)
    .sort((a, b) => a - b);
  const pick = (key: "model" | "seasonal_naive" | "ets") =>
    days.map((d) => metrics.by_horizon[String(d)]?.[key].mase ?? null);
  return { days, model: pick("model"), seasonalNaive: pick("seasonal_naive"), ets: pick("ets") };
}
