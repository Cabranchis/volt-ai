import type { ForecastPoint } from "./data/types";
import { logNormalOf } from "./spikes";

/** Longest window measured in the backtest: the price horizon is 14 and the window starts on the issue day (horizon 3). */
export const MAX_WINDOW_DAYS = 12;
/** Draws per simulation: the 5th and 95th percentiles of the total move less than 1 % between seeds. */
export const DRAWS = 4000;
/**
 * What the backtest measured (pipeline/research/run_cost_window.py, results/cost_window_2026-10-26.json, windows from the
 * day the forecast is issued): the correlation between days that made the range of a window cover the real mean price closest
 * to 80 % on average, the coverage it gave for windows of 3, 7 and 12 days, and where the misses fell.
 */
export const WINDOW_BACKTEST = {
  rho: 0.7,
  coverage: { 3: 0.843, 7: 0.824, 12: 0.784 },
  /** Share of windows whose real mean price fell below P10 / above P90, from the shortest to the longest window. */
  belowRange: [0.137, 0.176],
  aboveRange: [0.02, 0.039],
  date: "2026-10-26",
} as const;
export const SEED = 20261026;

export interface CostInput {
  /** Forecast days in the window, in order. */
  points: readonly ForecastPoint[];
  /** Energy bought per day, in MWh. */
  mwhPerDay: number;
  /** Correlation between the price errors of two different days, 0 to 1 (measured in the backtest). */
  rho: number;
  /** Price of the contract to compare with, in COP/kWh. */
  contractCopKwh?: number | null;
  draws?: number;
  seed?: number;
}

export interface Quantiles {
  p10: number;
  p50: number;
  p90: number;
}

export interface CostDay extends Quantiles {
  day: string;
  horizon: number;
  /** Cost of the day's volume in millions of COP, at the day's P10, P50 and P90 price. */
  costP10: number;
  costP50: number;
  costP90: number;
}

export interface CostResult {
  days: CostDay[];
  /** Days dropped because their band could not be read. */
  skipped: number;
  totalMwh: number;
  /** Total cost of the window in millions of COP. */
  cost: Quantiles & { p95: number };
  /** Volume-weighted mean price of the window in COP/kWh. */
  meanPrice: Quantiles;
  /** Present when a contract price was given. */
  contract: null | {
    /** Cost of the same energy at the contract price, in millions of COP. */
    cost: number;
    /** P(spot cost > contract cost). */
    probSpotHigher: number;
    /** Expected spot cost minus contract cost, in millions of COP (positive: spot costs more). */
    expectedGap: number;
  };
}

/** Small seeded generator (mulberry32): the same input always gives the same simulation. */
export function seededRandom(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A standard normal draw by the Box-Muller transform. */
function normal(random: () => number): number {
  const u = 1 - random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * random());
}

/** Linear-interpolated percentile (0 to 1) of a sorted array. */
export function percentile(sorted: Float64Array, q: number): number {
  const position = (sorted.length - 1) * q;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  const low = sorted[lower] as number;
  const high = sorted[upper] as number;
  return low + (high - low) * (position - lower);
}

/** The forecast days from `today` on (an ISO date), at most `days` of them. */
export function windowDays(points: readonly ForecastPoint[], today: string, days: number): ForecastPoint[] {
  return points.filter((p) => p.day >= today).slice(0, Math.max(0, Math.floor(days)));
}

/**
 * A number typed by a person: digits with at most one decimal mark, a dot or a comma. A group of
 * exactly three digits after the mark ("1.000", "1,000") could be a thousands separator or a
 * decimal, and guessing wrong is off by a factor of 1000, so it is rejected (NaN). "0,125" is fine.
 */
export function parseAmount(text: string): number {
  const clean = text.trim();
  if (/^\d+$/.test(clean)) return Number(clean);
  const match = /^(\d+)[.,](\d+)$/.exec(clean);
  if (!match) return Number.NaN;
  if ((match[2] as string).length === 3 && match[1] !== "0") return Number.NaN;
  return Number(`${match[1]}.${match[2]}`);
}

export type InputIssue = "volume" | "days" | "contract";

/** What is wrong with the inputs, or null when they can be used. */
export function checkInputs(mwhPerDay: number, days: number, contract: number | null): InputIssue | null {
  if (!Number.isFinite(mwhPerDay) || mwhPerDay <= 0 || mwhPerDay > 1_000_000) return "volume";
  if (!Number.isInteger(days) || days < 1 || days > MAX_WINDOW_DAYS) return "days";
  if (contract !== null && (!Number.isFinite(contract) || contract <= 0 || contract > 100_000)) return "contract";
  return null;
}

/**
 * Cost of buying `mwhPerDay` every day of the window on the spot market, with a range.
 *
 * Each day's price is the log-normal with the forecast's median (P50) and the log-spread between its
 * P10 and P90 (the same reading the price spike panel uses). Daily bands cannot be added up: the P10 of the window is the sum of
 * the daily P10 only if the days move together perfectly. So the days share a common factor, with
 * correlation `rho` between the errors of any two days, and the window is simulated. The rho and
 * the coverage it gives are measured in the backtest (docs/model-card.md).
 */
export function simulateCost(input: CostInput): CostResult | null {
  const { mwhPerDay, rho } = input;
  const draws = input.draws ?? DRAWS;
  const dists: { point: ForecastPoint; mu: number; sigma: number }[] = [];
  let skipped = 0;
  for (const point of input.points) {
    const dist = logNormalOf(point);
    if (dist === null) skipped += 1;
    else dists.push({ point, ...dist });
  }
  if (dists.length === 0 || !(mwhPerDay > 0) || !(rho >= 0 && rho <= 1)) return null;

  // 1 MWh = 1000 kWh, so MWh x COP/kWh / 1000 is millions of COP.
  const factor = mwhPerDay / 1000;
  const random = seededRandom(input.seed ?? SEED);
  const shared = Math.sqrt(rho);
  const own = Math.sqrt(1 - rho);
  const totals = new Float64Array(draws);
  for (let d = 0; d < draws; d++) {
    const common = normal(random);
    let total = 0;
    for (const { mu, sigma } of dists) total += Math.exp(mu + sigma * (shared * common + own * normal(random)));
    totals[d] = total * factor;
  }
  const sorted = Float64Array.from(totals).sort();

  const n = dists.length;
  const totalMwh = mwhPerDay * n;
  const perPrice = 1000 / totalMwh; // millions of COP for the whole window -> COP/kWh
  const cost = {
    p10: percentile(sorted, 0.1),
    p50: percentile(sorted, 0.5),
    p90: percentile(sorted, 0.9),
    p95: percentile(sorted, 0.95),
  };

  let contract: CostResult["contract"] = null;
  const price = input.contractCopKwh;
  if (price !== undefined && price !== null && price > 0) {
    const contractCost = (totalMwh * price) / 1000;
    let higher = 0;
    let sum = 0;
    for (let d = 0; d < draws; d++) {
      if ((totals[d] as number) > contractCost) higher += 1;
      sum += totals[d] as number;
    }
    contract = { cost: contractCost, probSpotHigher: higher / draws, expectedGap: sum / draws - contractCost };
  }

  return {
    days: dists.map(({ point }) => ({
      day: point.day,
      horizon: point.horizon,
      p10: point.p10,
      p50: point.p50,
      p90: point.p90,
      costP10: point.p10 * factor,
      costP50: point.p50 * factor,
      costP90: point.p90 * factor,
    })),
    skipped,
    totalMwh,
    cost,
    meanPrice: { p10: cost.p10 * perPrice, p50: cost.p50 * perPrice, p90: cost.p90 * perPrice },
    contract,
  };
}
