export interface HistoryInput {
  dates: readonly string[];
  values: readonly (number | null)[];
}

export interface ForecastInput {
  day: string;
  p10: number;
  p50: number;
  p90: number;
}

export interface AssembledForecast {
  dates: string[];
  observed: (number | null)[];
  median: (number | null)[];
  lower: (number | null)[];
  width: (number | null)[];
  /** Index of the last observed point on the shared date axis. */
  lastObservedIndex: number;
  lastObservedDate: string;
}

/**
 * Lay history and forecast on one date axis.
 *
 * - The forecast starts the day after the last observed value; earlier forecast days are dropped.
 * - The median and the band start at the last observed point, so the line and the fan open
 *   from the real value instead of jumping.
 * - `rangeDays` limits how much history is shown (null shows everything).
 * Returns null when there is no observed value at all.
 */
export function assembleForecast(
  history: HistoryInput,
  forecast: readonly ForecastInput[],
  rangeDays: number | null,
): AssembledForecast | null {
  let last = -1;
  for (let i = history.values.length - 1; i >= 0; i--) {
    if (history.values[i] !== null && history.values[i] !== undefined) {
      last = i;
      break;
    }
  }
  if (last < 0) return null;

  const lastDate = history.dates[last] as string;
  const start = rangeDays === null ? 0 : Math.max(0, last - rangeDays + 1);
  const histDates = history.dates.slice(start, last + 1);
  const histValues = history.values.slice(start, last + 1);
  const future = forecast.filter((p) => p.day > lastDate);

  const nHistory = histDates.length;
  const total = nHistory + future.length;
  const empty = (): (number | null)[] => new Array<number | null>(total).fill(null);

  const observed = empty();
  histValues.forEach((value, i) => {
    observed[i] = value ?? null;
  });

  const median = empty();
  const lower = empty();
  const width = empty();
  const anchor = histValues[nHistory - 1] ?? null;
  if (future.length > 0 && anchor !== null) {
    median[nHistory - 1] = anchor;
    lower[nHistory - 1] = anchor;
    width[nHistory - 1] = 0;
  }
  future.forEach((point, i) => {
    median[nHistory + i] = point.p50;
    lower[nHistory + i] = point.p10;
    width[nHistory + i] = point.p90 - point.p10;
  });

  return {
    dates: [...histDates, ...future.map((p) => p.day)],
    observed,
    median,
    lower,
    width,
    lastObservedIndex: nHistory - 1,
    lastObservedDate: lastDate,
  };
}

export const RANGE_DAYS = { "3m": 92, "1y": 365, "3y": 1096, all: null } as const;
export type RangeKey = keyof typeof RANGE_DAYS;
