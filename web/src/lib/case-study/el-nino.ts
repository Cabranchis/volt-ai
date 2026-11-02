import type { SeriesFrame } from "@/lib/data/types";
import data from "./el-nino.json";

export interface CaseRow {
  day: string;
  y: number | null;
  p10: number;
  p50: number;
  p90: number;
  ets: number;
}

export interface CasePoint {
  origin: string;
  scores: { model: number; ets: number; naive: number; coverage: number };
  history: { day: string; y: number }[];
  rows: CaseRow[];
}

export interface Regime {
  origins: number;
  model: number;
  ets: number;
  naive: number;
  coverage: number;
  won: number;
}

export interface MonthProfile {
  price: number | null;
  reservoirMin: number | null;
  inflows: number | null;
  thermal: number | null;
  oni: number | null;
}

export const REGIME_KEYS = ["nino-2023", "crisis-2024", "calm", "nino-2026", "all"] as const;
export type RegimeKey = (typeof REGIME_KEYS)[number];

export const CASE_STUDY = data as unknown as {
  runId: string;
  dataEnd: string;
  regimes: Record<RegimeKey, Regime>;
  cases: CasePoint[];
  months: Record<string, MonthProfile>;
};

export interface CaseSeries {
  dates: string[];
  observed: (number | null)[];
  median: (number | null)[];
  lower: (number | null)[];
  width: (number | null)[];
  ets: (number | null)[];
  /** Index of the forecast origin on the date axis. */
  originIndex: number;
}

/**
 * Lay the days before the origin and the 14 forecast days on one axis. Observed prices cover both
 * halves (what was known, then what happened); the median, the band and ETS start at the origin so
 * the lines open from the last known price.
 */
export function buildCaseSeries(point: CasePoint): CaseSeries {
  const past = point.history.filter((h) => h.day <= point.origin);
  const originValue = past.length > 0 ? (past[past.length - 1] as { y: number }).y : null;
  const dates = [...past.map((h) => h.day), ...point.rows.map((r) => r.day)];
  const originIndex = past.length - 1;
  const total = dates.length;
  const blank = (): (number | null)[] => new Array<number | null>(total).fill(null);

  const observed = blank();
  past.forEach((h, i) => (observed[i] = h.y));
  point.rows.forEach((r, i) => (observed[past.length + i] = r.y));

  const median = blank();
  const lower = blank();
  const width = blank();
  const ets = blank();
  if (originValue !== null && originIndex >= 0) {
    median[originIndex] = originValue;
    lower[originIndex] = originValue;
    width[originIndex] = 0;
    ets[originIndex] = originValue;
  }
  point.rows.forEach((r, i) => {
    const at = past.length + i;
    median[at] = r.p50;
    lower[at] = r.p10;
    width[at] = r.p90 - r.p10;
    ets[at] = r.ets;
  });
  return { dates, observed, median, lower, width, ets, originIndex };
}

/** Days the forecast was inside the P10 to P90 band, from the production score (not the rounded rows). */
export function insideBand(point: CasePoint): { inside: number; total: number } {
  const total = point.rows.filter((r) => r.y !== null).length;
  return { inside: Math.round(point.scores.coverage * total), total };
}

/** The monthly ONI is stored on day 1 of its month and published about this many days later. */
export const ONI_LAG_DAYS = 75;

const addDays = (iso: string, days: number): string => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
};

/** Months, newest first, with at least `minDays` days of price, so a month is never a single day. */
export function lastFullMonth(frame: SeriesFrame, minDays = 15): string | null {
  const counts = new Map<string, number>();
  const price = frame.series.price_mean_cop_kwh ?? [];
  frame.dates.forEach((d, i) => {
    if (price[i] !== null && price[i] !== undefined) counts.set(d.slice(0, 7), (counts.get(d.slice(0, 7)) ?? 0) + 1);
  });
  const months = [...counts.keys()].sort().reverse();
  return months.find((m) => (counts.get(m) ?? 0) >= minDays) ?? months[0] ?? null;
}

/**
 * Market profile of one calendar month ("2026-10") from the live series: mean price, lowest
 * reservoir level, mean inflows against the historical mean, thermal share of generation (sum over
 * sum, on days with both), and the last ONI already published at the end of that month.
 */
export function monthProfile(frame: SeriesFrame, month: string): MonthProfile {
  const idx = frame.dates.map((d, i) => (d.startsWith(month) ? i : -1)).filter((i) => i >= 0);
  const col = (name: string) => frame.series[name] ?? [];
  const values = (name: string) =>
    idx.map((i) => col(name)[i]).filter((v): v is number => v !== null && v !== undefined);
  const mean = (xs: number[]) => (xs.length > 0 ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

  let thermal = 0;
  let total = 0;
  for (const i of idx) {
    const a = col("gen_thermal_kwh")[i];
    const b = col("gen_total_kwh")[i];
    if (a !== null && a !== undefined && b !== null && b !== undefined) {
      thermal += a;
      total += b;
    }
  }

  let oni: number | null = null;
  if (idx.length > 0) {
    const cutoff = addDays(frame.dates[idx[idx.length - 1] as number] as string, -ONI_LAG_DAYS);
    for (let i = frame.dates.length - 1; i >= 0; i--) {
      const v = col("oni")[i];
      if ((frame.dates[i] as string) <= cutoff && v !== null && v !== undefined) {
        oni = v;
        break;
      }
    }
  }
  const reservoir = values("reservoir_pct");
  const inflows = mean(values("inflows_pct"));
  return {
    price: mean(values("price_mean_cop_kwh")),
    reservoirMin: reservoir.length > 0 ? Math.min(...reservoir) * 100 : null,
    inflows: inflows === null ? null : inflows * 100,
    thermal: total > 0 ? (thermal / total) * 100 : null,
    oni,
  };
}
