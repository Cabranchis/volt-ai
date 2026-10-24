import { addDays } from "./format";
import type { SeriesFrame, SeriesName } from "./data/types";

/** Stack order of the generation mix, bottom to top. Validated for colour-vision separation (docs/design-system.md). */
export const MIX_ORDER = ["thermal", "hydro", "wind", "solar", "cogen", "other"] as const;
export type MixKey = (typeof MIX_ORDER)[number];

export const MIX_SERIES: Record<MixKey, SeriesName> = {
  thermal: "gen_thermal_kwh",
  hydro: "gen_hydro_kwh",
  wind: "gen_wind_kwh",
  solar: "gen_solar_kwh",
  cogen: "gen_cogen_kwh",
  other: "gen_other_kwh",
};

export const MIX_SERIES_NAMES = MIX_ORDER.map((k) => MIX_SERIES[k]);

export function dayIndex(frame: SeriesFrame, day: string): number {
  // Dates are sorted ISO strings, so a binary search is exact and cheap on 3k points.
  let lo = 0;
  let hi = frame.dates.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const value = frame.dates[mid] as string;
    if (value === day) return mid;
    if (value < day) lo = mid + 1;
    else hi = mid - 1;
  }
  return -1;
}

export function valueOn(frame: SeriesFrame, name: string, day: string): number | null {
  const i = dayIndex(frame, day);
  return i < 0 ? null : (frame.series[name]?.[i] ?? null);
}

export function lastDayOf(frame: SeriesFrame, name: string): string | null {
  const column = frame.series[name];
  if (!column) return null;
  for (let i = column.length - 1; i >= 0; i--) {
    if (column[i] !== null && column[i] !== undefined) return frame.dates[i] as string;
  }
  return null;
}

export interface Kpi {
  day: string;
  value: number;
  /** Value exactly `daysBack` days earlier, if that day exists. */
  previous: number | null;
  /** value - previous. */
  delta: number | null;
}

export function kpi(frame: SeriesFrame, name: string, daysBack = 7): Kpi | null {
  const day = lastDayOf(frame, name);
  if (!day) return null;
  const value = valueOn(frame, name, day);
  if (value === null) return null;
  const previous = valueOn(frame, name, addDays(day, -daysBack));
  return { day, value, previous, delta: previous === null ? null : value - previous };
}

export type MixShares = Record<MixKey, number>;

/** Share of each source in the day's generation. Shares sum to 1 over the six categories. */
export function mixShares(frame: SeriesFrame, day: string): MixShares | null {
  const values = MIX_ORDER.map((key) => valueOn(frame, MIX_SERIES[key], day));
  if (values.some((v) => v === null)) return null;
  const total = (values as number[]).reduce((a, b) => a + b, 0);
  if (total <= 0) return null;
  return Object.fromEntries(MIX_ORDER.map((key, i) => [key, (values[i] as number) / total])) as MixShares;
}

export type OniPhase = "strongNino" | "nino" | "neutral" | "nina";

/** NOAA's convention: +0.5 or more is El Niño, -0.5 or less is La Niña. 1.5 and above is called strong. */
export function oniPhase(value: number): OniPhase {
  if (value >= 1.5) return "strongNino";
  if (value >= 0.5) return "nino";
  if (value <= -0.5) return "nina";
  return "neutral";
}

/** Mean of the first n forecast medians. */
export function meanOfFirst(points: readonly { p50: number }[], n: number): number | null {
  const slice = points.slice(0, n);
  return slice.length === 0 ? null : slice.reduce((a, p) => a + p.p50, 0) / slice.length;
}

export function weekdayProfile(
  frame: SeriesFrame,
  name: string,
  lastDays: number,
): { dow: number; mean: number }[] {
  const column = frame.series[name];
  if (!column) return [];
  const sums = new Array<number>(7).fill(0);
  const counts = new Array<number>(7).fill(0);
  const end = column.length - 1;
  for (let i = end; i >= 0 && end - i < lastDays; i--) {
    const value = column[i];
    if (value === null || value === undefined) continue;
    // 0 = Monday ... 6 = Sunday, from the calendar date (UTC avoids time-zone drift).
    const dow = (new Date(`${frame.dates[i]}T00:00:00Z`).getUTCDay() + 6) % 7;
    sums[dow] = (sums[dow] as number) + value;
    counts[dow] = (counts[dow] as number) + 1;
  }
  return sums.map((sum, dow) => ({ dow, mean: (counts[dow] as number) > 0 ? sum / (counts[dow] as number) : 0 }));
}

/** Calendar months of a daily series as mean shares of the generation mix, for the stacked area. */
export function monthlyMix(frame: SeriesFrame): { months: string[]; shares: Record<MixKey, number[]> } {
  const buckets = new Map<string, number[]>();
  const columns = MIX_ORDER.map((key) => frame.series[MIX_SERIES[key]] ?? []);
  frame.dates.forEach((date, i) => {
    const row = columns.map((c) => c[i]);
    if (row.some((v) => v === null || v === undefined)) return;
    const month = date.slice(0, 7);
    const bucket = buckets.get(month) ?? new Array<number>(MIX_ORDER.length).fill(0);
    row.forEach((v, k) => {
      bucket[k] = (bucket[k] as number) + (v as number);
    });
    buckets.set(month, bucket);
  });
  const months = [...buckets.keys()].sort();
  const shares = Object.fromEntries(MIX_ORDER.map((k) => [k, [] as number[]])) as Record<MixKey, number[]>;
  for (const month of months) {
    const bucket = buckets.get(month) as number[];
    const total = bucket.reduce((a, b) => a + b, 0);
    MIX_ORDER.forEach((key, k) => shares[key].push(total > 0 ? (bucket[k] as number) / total : 0));
  }
  return { months, shares };
}
