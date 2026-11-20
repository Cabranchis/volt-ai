import type { TrackRow } from "./data/types";

/**
 * Whether the live record (forecasts as first issued, next to what happened) shows a band that
 * stopped covering. It is advice for the owner, not a health status: the site keeps working and a
 * band that misses for a week is not a broken platform. The watchdog turns `low` into one issue.
 *
 * The unit is the target day, not the forecast: the forecasts for one day come from many origins
 * and share the same outcome, so counting them separately would make one odd day look like a
 * trend. Each settled day scores the share of its forecasts that fell inside P10 to P90, and the
 * result is the mean over the `WINDOW_DAYS` calendar days that end on the last settled day. Days
 * without a settled outcome are skipped, so the window can hold fewer settled days than that.
 *
 * The limits are a judgement, not a fitted value: the live record had 26 days when they were set,
 * and its weekly coverage moved between 45 % and 100 % (docs/model-experiments.md, "The live
 * demand range"). A week is therefore noise; a month well under the nominal 80 % is not. They are
 * written down in docs/runbook.md and should be reviewed once the record has a year.
 */
export const WINDOW_DAYS = 28;
/** Fewer settled days than this and the window says nothing yet. */
export const MIN_SCORED_DAYS = 21;
/** Mean share inside the band below which the window is reported. The band is built for 0.80. */
export const LOW_COVERAGE = 0.55;

/** Named `verdict`, not `status`, so a search for `"status":"ok"` in the health body only finds the platform status and the datasets. */
export type LiveVerdict = "ok" | "low" | "insufficient";

export interface LiveWindow {
  verdict: LiveVerdict;
  /** Settled target days inside the window. */
  scoredDays: number;
  /** Mean over those days of the share of forecasts inside P10 to P90, or null when none. */
  coverage: number | null;
  /** First and last target day of the window. */
  from: string | null;
  to: string | null;
}

const DAY_MS = 86_400_000;

export function assessLiveRecord(rows: readonly TrackRow[]): LiveWindow {
  const settled = rows.filter((r) => r.actual !== null && Number.isFinite(r.actual) && r.actual > 0);
  const lastDay = settled.reduce<string | null>((max, r) => (max === null || r.day > max ? r.day : max), null);
  if (lastDay === null) return { verdict: "insufficient", scoredDays: 0, coverage: null, from: null, to: null };

  const firstDay = new Date(Date.parse(`${lastDay}T00:00:00Z`) - (WINDOW_DAYS - 1) * DAY_MS).toISOString().slice(0, 10);
  const perDay = new Map<string, { inside: number; total: number }>();
  for (const r of settled) {
    if (r.day < firstDay) continue;
    const actual = r.actual as number;
    const entry = perDay.get(r.day) ?? { inside: 0, total: 0 };
    entry.total += 1;
    if (actual >= r.p10 && actual <= r.p90) entry.inside += 1;
    perDay.set(r.day, entry);
  }

  const shares = [...perDay.values()].map((d) => d.inside / d.total);
  const days = [...perDay.keys()].sort();
  const coverage = shares.length > 0 ? shares.reduce((sum, s) => sum + s, 0) / shares.length : null;
  const verdict: LiveVerdict =
    shares.length < MIN_SCORED_DAYS || coverage === null ? "insufficient" : coverage < LOW_COVERAGE ? "low" : "ok";
  return { verdict, scoredDays: shares.length, coverage, from: days[0] ?? null, to: days[days.length - 1] ?? null };
}
