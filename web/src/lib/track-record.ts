import type { TrackRow } from "./data/types";

export interface BucketScore {
  /** First and last horizon of the bucket, in days ahead. */
  from: number;
  to: number;
  n: number;
  /** Mean absolute percentage error of the P50, in percent. */
  mape: number;
  /** Same error of the naive reference, over the same forecasts. */
  naiveMape: number | null;
  /** Share of outcomes that fell inside the P10 to P90 band. */
  coverage: number;
}

export interface TrackRecord {
  /** Forecasts whose day is settled and could be compared with what happened. */
  scored: number;
  /** Forecasts logged for days XM has not settled yet. */
  pending: number;
  firstDay: string | null;
  lastDay: string | null;
  overall: BucketScore | null;
  buckets: BucketScore[];
  /** Share of scored forecasts whose P50 beat the naive reference. */
  winShare: number | null;
}

export const HORIZON_BUCKETS: readonly (readonly [number, number])[] = [
  [1, 3],
  [4, 7],
  [8, 14],
  [15, 30],
];

const ape = (forecast: number, actual: number): number => Math.abs(forecast - actual) / Math.abs(actual);
const mean = (values: readonly number[]): number => values.reduce((sum, v) => sum + v, 0) / values.length;

function score(rows: readonly (TrackRow & { actual: number })[], from: number, to: number): BucketScore | null {
  if (rows.length === 0) return null;
  const withNaive = rows.filter((r) => r.naive !== null && r.naive !== undefined);
  return {
    from,
    to,
    n: rows.length,
    mape: 100 * mean(rows.map((r) => ape(r.p50, r.actual))),
    naiveMape: withNaive.length > 0 ? 100 * mean(withNaive.map((r) => ape(r.naive as number, r.actual))) : null,
    coverage: rows.filter((r) => r.actual >= r.p10 && r.actual <= r.p90).length / rows.length,
  };
}

const settled = (r: TrackRow): r is TrackRow & { actual: number } =>
  r.actual !== null && Number.isFinite(r.actual) && r.actual > 0;

/** Compares the forecasts as first issued with what happened. Nothing here is refitted or revised. */
export function scoreTrackRecord(rows: readonly TrackRow[]): TrackRecord {
  const scoredRows = rows.filter(settled);
  const buckets = HORIZON_BUCKETS.map(([from, to]) =>
    score(
      scoredRows.filter((r) => r.horizon >= from && r.horizon <= to),
      from,
      to,
    ),
  ).filter((b): b is BucketScore => b !== null);
  const compared = scoredRows.filter((r) => r.naive !== null && r.naive !== undefined);
  const days = scoredRows.map((r) => r.day).sort();
  return {
    scored: scoredRows.length,
    pending: rows.length - scoredRows.length,
    firstDay: days[0] ?? null,
    lastDay: days[days.length - 1] ?? null,
    overall: score(scoredRows, 1, Math.max(0, ...scoredRows.map((r) => r.horizon))),
    buckets,
    winShare:
      compared.length > 0
        ? compared.filter((r) => ape(r.p50, r.actual) < ape(r.naive as number, r.actual)).length / compared.length
        : null,
  };
}
