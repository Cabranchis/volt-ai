import type { ForecastPoint } from "./data/types";

/** Absolute price level (COP/kWh) above which the spot market is considered expensive. */
export const SPIKE_LEVEL = 500;
/** A day counts as a rise when it is this many times the mean of the last 30 settled days. */
export const SPIKE_RISE = 1.3;
export const Z90 = 1.2815515655446004;
const MEAN_WINDOW = 30;

export interface SpikeDay {
  day: string;
  horizon: number;
  /** P(price > SPIKE_LEVEL) */
  aboveLevel: number;
  /** P(price > SPIKE_RISE x the 30-day mean) */
  rise: number;
}

export interface SpikeOutlook {
  baseline: number;
  days: SpikeDay[];
}

/** Standard normal CDF (Abramowitz and Stegun 7.1.26, error below 1.5e-7). */
export function normalCdf(z: number): number {
  const x = Math.abs(z) / Math.SQRT2;
  const t = 1 / (1 + 0.3275911 * x);
  const poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))));
  const erf = 1 - poly * Math.exp(-x * x);
  return 0.5 * (1 + (z < 0 ? -erf : erf));
}

/** Mean of the last settled prices (up to 30), or null when there are fewer than 20. */
export function recentMean(values: readonly (number | null)[]): number | null {
  const recent: number[] = [];
  for (let i = values.length - 1; i >= 0 && recent.length < MEAN_WINDOW; i--) {
    const v = values[i];
    if (v !== null && v !== undefined && Number.isFinite(v) && v > 0) recent.push(v);
  }
  if (recent.length < 20) return null;
  return recent.reduce((sum, v) => sum + v, 0) / recent.length;
}

/** The log-normal with a day's median (P50) and the log-scale spread between its P10 and P90, or null if the band is unusable. */
export function logNormalOf(point: Pick<ForecastPoint, "p10" | "p50" | "p90">): { mu: number; sigma: number } | null {
  if (!(point.p10 > 0) || !(point.p50 > 0) || !(point.p90 > point.p10)) return null;
  return {
    mu: Math.log(point.p50),
    sigma: Math.max((Math.log(point.p90) - Math.log(point.p10)) / (2 * Z90), 1e-3),
  };
}

/**
 * P(price > threshold) read from the forecast's own P10/P50/P90, taken as a log-normal
 * distribution. The research backtest (docs/model-experiments.md) scored it for the two events
 * shown here; it is not offered for much higher levels, where it did not beat persistence.
 */
export function exceedance(point: Pick<ForecastPoint, "p10" | "p50" | "p90">, threshold: number): number | null {
  const dist = logNormalOf(point);
  if (dist === null || !(threshold > 0)) return null;
  return 1 - normalCdf((Math.log(threshold) - dist.mu) / dist.sigma);
}

export function spikeOutlook(
  points: readonly ForecastPoint[],
  history: readonly (number | null)[],
): SpikeOutlook | null {
  const baseline = recentMean(history);
  if (baseline === null) return null;
  const days: SpikeDay[] = [];
  for (const p of points) {
    const aboveLevel = exceedance(p, SPIKE_LEVEL);
    const rise = exceedance(p, SPIKE_RISE * baseline);
    if (aboveLevel === null || rise === null) continue;
    days.push({ day: p.day, horizon: p.horizon, aboveLevel, rise });
  }
  return days.length > 0 ? { baseline, days } : null;
}

export type SpikeEvent = "aboveLevel" | "rise";

/** The day with the highest probability for one event. */
export function peakDay(outlook: SpikeOutlook, event: SpikeEvent): SpikeDay {
  return outlook.days.reduce((best, d) => (d[event] > best[event] ? d : best), outlook.days[0] as SpikeDay);
}
