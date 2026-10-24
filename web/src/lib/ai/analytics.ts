import type { SeriesFrame, SeriesName } from "@/lib/data/types";
import { addDays } from "@/lib/format";
import { dayIndex, kpi, lastDayOf, mixShares, MIX_ORDER } from "@/lib/insights";

/** Unit conversion for the numbers the analyst sees, so the model never converts kWh itself. */
export const SERIES_META: Record<SeriesName, { unit: string; scale: number; decimals: number }> = {
  demand_kwh: { unit: "GWh/day", scale: 1e6, decimals: 1 },
  price_mean_cop_kwh: { unit: "COP/kWh", scale: 1, decimals: 0 },
  price_max_cop_kwh: { unit: "COP/kWh", scale: 1, decimals: 0 },
  reservoir_pct: { unit: "% of capacity", scale: 0.01, decimals: 1 },
  reservoir_kwh: { unit: "GWh", scale: 1e6, decimals: 0 },
  inflows_kwh: { unit: "GWh/day", scale: 1e6, decimals: 0 },
  inflows_pct: { unit: "% of historical mean", scale: 0.01, decimals: 0 },
  inflows_hist_mean_kwh: { unit: "GWh/day", scale: 1e6, decimals: 0 },
  gen_total_kwh: { unit: "GWh/day", scale: 1e6, decimals: 1 },
  gen_hydro_kwh: { unit: "GWh/day", scale: 1e6, decimals: 1 },
  gen_thermal_kwh: { unit: "GWh/day", scale: 1e6, decimals: 1 },
  gen_solar_kwh: { unit: "GWh/day", scale: 1e6, decimals: 1 },
  gen_wind_kwh: { unit: "GWh/day", scale: 1e6, decimals: 1 },
  gen_cogen_kwh: { unit: "GWh/day", scale: 1e6, decimals: 1 },
  gen_other_kwh: { unit: "GWh/day", scale: 1e6, decimals: 1 },
  weather_temp_c: { unit: "degrees C", scale: 1, decimals: 1 },
  weather_precip_mm: { unit: "mm/day", scale: 1, decimals: 1 },
  oni: { unit: "degrees C anomaly (ONI)", scale: 1, decimals: 2 },
};

const round = (value: number, decimals: number): number => {
  const f = 10 ** decimals;
  return Math.round(value * f) / f;
};

export const display = (name: SeriesName, value: number): number => {
  const meta = SERIES_META[name];
  return round(value / meta.scale, meta.decimals);
};

interface Point {
  day: string;
  value: number;
}

function pointsOf(frame: SeriesFrame, name: SeriesName, from?: string, to?: string): Point[] {
  const column = frame.series[name] ?? [];
  const points: Point[] = [];
  frame.dates.forEach((day, i) => {
    const value = column[i];
    if (value === null || value === undefined) return;
    if (from && day < from) return;
    if (to && day > to) return;
    points.push({ day, value });
  });
  return points;
}

export interface SeriesSummary {
  series: SeriesName;
  unit: string;
  from: string;
  to: string;
  days: number;
  first: { day: string; value: number };
  last: { day: string; value: number };
  min: { day: string; value: number };
  max: { day: string; value: number };
  mean: number;
  /** About 24 evenly spaced points, enough to describe a trend without flooding the model. */
  sample: { day: string; value: number }[];
}

export function summariseSeries(
  frame: SeriesFrame,
  name: SeriesName,
  from?: string,
  to?: string,
): SeriesSummary | { error: string } {
  const points = pointsOf(frame, name, from, to);
  if (points.length === 0) return { error: "No data for that series and period." };
  const at = (p: Point) => ({ day: p.day, value: display(name, p.value) });
  const min = points.reduce((a, b) => (b.value < a.value ? b : a));
  const max = points.reduce((a, b) => (b.value > a.value ? b : a));
  const mean = points.reduce((s, p) => s + p.value, 0) / points.length;
  const step = Math.max(1, Math.floor(points.length / 24));
  const sample = points.filter((_, i) => i % step === 0 || i === points.length - 1).map(at);
  return {
    series: name,
    unit: SERIES_META[name].unit,
    from: (points[0] as Point).day,
    to: (points[points.length - 1] as Point).day,
    days: points.length,
    first: at(points[0] as Point),
    last: at(points[points.length - 1] as Point),
    min: at(min),
    max: at(max),
    mean: display(name, mean),
    sample,
  };
}

export interface PeriodComparison {
  series: SeriesName;
  unit: string;
  a: { from: string; to: string; days: number; mean: number };
  b: { from: string; to: string; days: number; mean: number };
  /** (b - a) / a, in percent. Null when a is zero. */
  changePercent: number | null;
}

export function comparePeriods(
  frame: SeriesFrame,
  name: SeriesName,
  a: { from: string; to: string },
  b: { from: string; to: string },
): PeriodComparison | { error: string } {
  const side = (range: { from: string; to: string }) => {
    const points = pointsOf(frame, name, range.from, range.to);
    if (points.length === 0) return null;
    const mean = points.reduce((s, p) => s + p.value, 0) / points.length;
    return { from: range.from, to: range.to, days: points.length, mean };
  };
  const sa = side(a);
  const sb = side(b);
  if (!sa || !sb) return { error: "One of the periods has no data." };
  return {
    series: name,
    unit: SERIES_META[name].unit,
    a: { ...sa, mean: display(name, sa.mean) },
    b: { ...sb, mean: display(name, sb.mean) },
    changePercent: sa.mean === 0 ? null : round(((sb.mean - sa.mean) / sa.mean) * 100, 1),
  };
}

export interface LastTimeResult {
  series: SeriesName;
  unit: string;
  threshold: number;
  latest: { day: string; value: number };
  /** The most recent earlier day at or above the threshold, if any. */
  previousDay: { day: string; value: number; daysAgo: number } | null;
  /** How many days in the last 365 were at or above the threshold. */
  daysAboveInLastYear: number;
}

/** "When was the last time the price was this high?" Threshold defaults to the latest value. */
export function lastTimeAtOrAbove(
  frame: SeriesFrame,
  name: SeriesName,
  thresholdDisplay?: number,
): LastTimeResult | { error: string } {
  const points = pointsOf(frame, name);
  const newest = points[points.length - 1];
  if (!newest) return { error: "No data for that series." };
  const meta = SERIES_META[name];
  const threshold = thresholdDisplay === undefined ? newest.value : thresholdDisplay * meta.scale;
  let previous: Point | null = null;
  for (let i = points.length - 1; i >= 0; i--) {
    const p = points[i] as Point;
    if (p.day === newest.day) continue;
    if (p.value >= threshold) {
      previous = p;
      break;
    }
  }
  const yearAgo = addDays(newest.day, -365);
  const daysAboveInLastYear = points.filter((p) => p.day > yearAgo && p.value >= threshold).length;
  const daysAgo = previous ? Math.round((Date.parse(newest.day) - Date.parse(previous.day)) / 86_400_000) : 0;
  return {
    series: name,
    unit: meta.unit,
    threshold: round(threshold / meta.scale, meta.decimals),
    latest: { day: newest.day, value: display(name, newest.value) },
    previousDay: previous ? { day: previous.day, value: display(name, previous.value), daysAgo } : null,
    daysAboveInLastYear,
  };
}

export interface Snapshot {
  demand: Record<string, unknown> | null;
  price: Record<string, unknown> | null;
  reservoir: Record<string, unknown> | null;
  inflows: Record<string, unknown> | null;
  oni: Record<string, unknown> | null;
  generationMixPercent: { latestDay: string; now: Record<string, number>; yearAgo: Record<string, number> | null } | null;
}

/** Latest figures with their change over a week and against a year ago. The analyst's first stop. */
export function snapshot(frame: SeriesFrame): Snapshot {
  const describe = (name: SeriesName, daysBack = 7): Record<string, unknown> | null => {
    const k = kpi(frame, name, daysBack);
    if (!k) return null;
    const yearAgoValue = dayIndex(frame, addDays(k.day, -365));
    const yearAgo = yearAgoValue < 0 ? null : (frame.series[name]?.[yearAgoValue] ?? null);
    return {
      unit: SERIES_META[name].unit,
      day: k.day,
      value: display(name, k.value),
      weekEarlier: k.previous === null ? null : display(name, k.previous),
      sameDayLastYear: yearAgo === null ? null : display(name, yearAgo),
    };
  };
  const mixDay = lastDayOf(frame, "gen_hydro_kwh");
  const pct = (shares: Record<string, number>) =>
    Object.fromEntries(MIX_ORDER.map((k) => [k, round((shares[k] as number) * 100, 1)]));
  const now = mixDay ? mixShares(frame, mixDay) : null;
  const ago = mixDay ? mixShares(frame, addDays(mixDay, -365)) : null;
  return {
    demand: describe("demand_kwh"),
    price: describe("price_mean_cop_kwh"),
    reservoir: describe("reservoir_pct"),
    inflows: describe("inflows_pct"),
    oni: describe("oni", 31),
    generationMixPercent: now && mixDay ? { latestDay: mixDay, now: pct(now), yearAgo: ago ? pct(ago) : null } : null,
  };
}
