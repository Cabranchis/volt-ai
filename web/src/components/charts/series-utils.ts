/** Trailing mean over `window` points, ignoring nulls. The first points use what is available. */
export function rollingMean(values: readonly (number | null)[], window: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  let count = 0;
  for (let i = 0; i < values.length; i++) {
    const incoming = values[i];
    if (incoming !== null && incoming !== undefined) {
      sum += incoming;
      count += 1;
    }
    const outgoing = values[i - window];
    if (i >= window && outgoing !== null && outgoing !== undefined) {
      sum -= outgoing;
      count -= 1;
    }
    out.push(count > 0 ? sum / count : null);
  }
  return out;
}

/**
 * Spread monthly values (stored on the first of the month) over the days they describe.
 * A value covers its month and stops at the end of the last published month, so the chart
 * never claims a value for a month that has not been published yet.
 */
export function spreadMonthly(
  dates: readonly string[],
  monthly: readonly (number | null)[],
): (number | null)[] {
  const byMonth = new Map<string, number>();
  dates.forEach((date, i) => {
    const value = monthly[i];
    if (value !== null && value !== undefined) byMonth.set(date.slice(0, 7), value);
  });
  return dates.map((date) => byMonth.get(date.slice(0, 7)) ?? null);
}

/** Keep the last `days` calendar days of a date axis. Returns the first index to keep. */
export function startIndexFor(dates: readonly string[], lastIndex: number, days: number | null): number {
  return days === null ? 0 : Math.max(0, lastIndex - days + 1);
}

export function lastNonNullIndex(values: readonly (number | null)[]): number {
  for (let i = values.length - 1; i >= 0; i--) {
    if (values[i] !== null && values[i] !== undefined) return i;
  }
  return -1;
}
