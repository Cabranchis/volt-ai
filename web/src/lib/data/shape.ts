import type { LatestPoint, SeriesFrame, SeriesRange } from "./types";

export interface SeriesRow {
  series: string;
  day: string;
  value: number;
}

/** Long rows (series, day, value) to the columnar frame the charts use. */
export function pivotRows(rows: readonly SeriesRow[], names: readonly string[]): SeriesFrame {
  const dates = [...new Set(rows.map((r) => r.day))].sort();
  const index = new Map(dates.map((d, i) => [d, i]));
  const series: Record<string, (number | null)[]> = Object.fromEntries(
    names.map((n) => [n, new Array<number | null>(dates.length).fill(null)]),
  );
  for (const row of rows) {
    const column = series[row.series];
    const i = index.get(row.day);
    if (column && i !== undefined) column[i] = row.value;
  }
  return { dates, series };
}

/** Restrict a frame to some series and an inclusive date range. Dates are ISO strings, so they compare as text. */
export function sliceFrame(
  frame: SeriesFrame,
  names: readonly string[],
  range: SeriesRange = {},
): SeriesFrame {
  const keep: number[] = [];
  frame.dates.forEach((date, i) => {
    if ((!range.from || date >= range.from) && (!range.to || date <= range.to)) keep.push(i);
  });
  const series: Record<string, (number | null)[]> = {};
  for (const name of names) {
    const column = frame.series[name];
    series[name] = column ? keep.map((i) => column[i] ?? null) : keep.map(() => null);
  }
  return { dates: keep.map((i) => frame.dates[i] as string), series };
}

/** Newest non-null value of each requested series. */
export function latestOf(
  frame: SeriesFrame,
  names: readonly string[],
): Record<string, LatestPoint | null> {
  const out: Record<string, LatestPoint | null> = {};
  for (const name of names) {
    const column = frame.series[name];
    out[name] = null;
    if (!column) continue;
    for (let i = column.length - 1; i >= 0; i--) {
      const value = column[i];
      if (value !== null && value !== undefined) {
        out[name] = { day: frame.dates[i] as string, value };
        break;
      }
    }
  }
  return out;
}
