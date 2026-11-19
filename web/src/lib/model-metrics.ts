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

// "Repeat the last price" is a single value, so it has errors but no band: no coverage. Optional and
// isolated with `catch`: a run without it (older, or the demand) or a malformed one still reads.
const pointMethod = z.object({ mape: z.number(), smape: z.number(), mase: z.number() });

const paired = z.object({
  mase_model: z.number(),
  mase_baseline: z.number(),
  mase_reduction_pct: z.number(),
  origins_won: z.number(),
  origins: z.number(),
  wilcoxon_p: z.number().nullable(),
  // 95 % interval of the mean MASE difference (model minus baseline); null with too few origins.
  mase_diff_ci95: z.tuple([z.number(), z.number()]).nullable().optional().catch(undefined),
});

const horizonMethod = z.object({ mase: z.number(), coverage_p10_p90: z.number() });
const bucketMethod = z.object({ mape: z.number() });

export const targetMetricsSchema = z.object({
  horizon: z.number(),
  n_origins: z.number(),
  first_origin: z.string(),
  last_origin: z.string(),
  nominal_coverage: z.number(),
  overall: z.object({
    model: method,
    seasonal_naive: method,
    ets: method,
    last_price: pointMethod.optional().catch(undefined),
  }),
  by_horizon: z.record(
    z.string(),
    z.object({
      model: horizonMethod,
      seasonal_naive: horizonMethod,
      ets: horizonMethod,
      last_price: z.object({ mase: z.number() }).optional().catch(undefined),
    }),
  ),
  by_bucket: z
    .record(
      z.string(),
      z.object({
        model: bucketMethod,
        seasonal_naive: bucketMethod,
        ets: bucketMethod,
        last_price: bucketMethod.optional().catch(undefined),
      }),
    )
    .optional()
    // Extra detail: if it is malformed the rest of the metrics still read.
    .catch(undefined),
  paired: z.object({ seasonal_naive: paired, ets: paired, last_price: paired.optional().catch(undefined) }),
  coverage: z.object({ raw: z.number(), calibrated: z.number().nullable() }),
});
export type TargetMetrics = z.infer<typeof targetMetricsSchema>;

export function parseTargetMetrics(metrics: Record<string, unknown>, target: string): TargetMetrics | null {
  const targets = metrics["targets"];
  if (typeof targets !== "object" || targets === null) return null;
  const parsed = targetMetricsSchema.safeParse((targets as Record<string, unknown>)[target]);
  return parsed.success ? parsed.data : null;
}

export type VerdictKind = "beats" | "ties" | "loses";

export interface Verdict {
  /**
   * `beats` and `loses` only when the interval of the MASE difference leaves zero out; with an
   * interval that includes zero, or none (too few origins), the honest word is `ties`.
   */
  kind: VerdictKind;
  /** True only for `beats`. */
  beats: boolean;
  /** True when the model's mean error is lower than the baseline's, whatever the interval says. */
  lower: boolean;
  /** Absolute size of the difference in MASE, in percent of the baseline's. */
  pct: number;
  won: number;
  total: number;
}

/**
 * Reads the paired comparison as a verdict. The model "beats" a baseline only when the 95 % interval
 * of the paired MASE difference (model minus baseline) is entirely below zero, and "loses" only when
 * it is entirely above; anything else is a tie that the data cannot separate.
 */
export function verdict(p: TargetMetrics["paired"]["seasonal_naive"]): Verdict {
  const ci = p.mase_diff_ci95;
  const kind: VerdictKind = !ci ? "ties" : ci[1] < 0 ? "beats" : ci[0] > 0 ? "loses" : "ties";
  return {
    kind,
    beats: kind === "beats",
    lower: p.mase_reduction_pct > 0,
    pct: Math.abs(p.mase_reduction_pct),
    won: p.origins_won,
    total: p.origins,
  };
}

/** MASE by day ahead as three aligned arrays, ordered by horizon. */
export function horizonSeries(metrics: TargetMetrics) {
  const days = Object.keys(metrics.by_horizon)
    .map(Number)
    .sort((a, b) => a - b);
  const pick = (key: "model" | "seasonal_naive" | "ets" | "last_price") =>
    days.map((d) => metrics.by_horizon[String(d)]?.[key]?.mase ?? null);
  return {
    days,
    model: pick("model"),
    seasonalNaive: pick("seasonal_naive"),
    ets: pick("ets"),
    lastPrice: pick("last_price"),
  };
}

export interface BucketError {
  /** Horizon bucket as the backtest labels it, such as "1-3". */
  label: string;
  model: number;
  seasonalNaive: number;
  ets: number;
  /** Error of repeating the last settled price; null when the run does not have it (the demand). */
  lastPrice: number | null;
}

/** Mean percentage error by horizon bucket, shortest horizon first. Empty when the run has none. */
export function bucketErrors(metrics: TargetMetrics): BucketError[] {
  return Object.entries(metrics.by_bucket ?? {})
    .map(([label, m]) => ({
      label,
      model: m.model.mape,
      seasonalNaive: m.seasonal_naive.mape,
      ets: m.ets.mape,
      lastPrice: m.last_price?.mape ?? null,
    }))
    .sort((a, b) => Number.parseInt(a.label, 10) - Number.parseInt(b.label, 10));
}
