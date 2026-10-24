import { formatGWh, formatNumber, formatPercent, formatDate } from "./format";
import type { Locale } from "./i18n/config";
import { oniPhase, type Kpi, type MixShares } from "./insights";

export interface SummaryInput {
  locale: Locale;
  demand: Kpi | null;
  price: Kpi | null;
  reservoir: Kpi | null;
  oni: Kpi | null;
  mix: MixShares | null;
  mixYearAgo: MixShares | null;
  /** Mean of the next seven demand forecast medians, in kWh, and the matching price in COP/kWh. */
  demandNextWeek: number | null;
  priceNextWeek: number | null;
}

const PHASE = {
  es: { strongNino: "un El Niño fuerte", nino: "El Niño", neutral: "condiciones neutras", nina: "La Niña" },
  en: { strongNino: "a strong El Niño", nino: "El Niño", neutral: "neutral conditions", nina: "La Niña" },
} as const;

/** "3.2 % above the same day a week earlier", or a plain "unchanged" under half a percent. */
function versusLastWeek(relPercent: number, locale: Locale): string {
  const pct = formatNumber(Math.abs(relPercent), locale, 1);
  if (Math.abs(relPercent) < 0.5) {
    return locale === "es"
      ? "prácticamente igual que la misma jornada de la semana anterior"
      : "essentially unchanged from the same day a week earlier";
  }
  if (locale === "es") {
    return `${pct} % ${relPercent > 0 ? "por encima" : "por debajo"} de la misma jornada de la semana anterior`;
  }
  return `${pct} % ${relPercent > 0 ? "above" : "below"} the same day a week earlier`;
}

/**
 * A short, factual summary built only from the numbers. It is what the page shows when the daily
 * briefing is missing, and the template the pipeline falls back to without a language model.
 * Every sentence is skipped when the figures it needs are missing, so it never invents a number.
 */
export function buildSummary(input: SummaryInput): string {
  const { locale } = input;
  const es = locale === "es";
  const sentences: string[] = [];

  if (input.demand) {
    const date = formatDate(input.demand.day, locale, "long");
    const rel =
      input.demand.previous !== null
        ? ((input.demand.value - input.demand.previous) / input.demand.previous) * 100
        : null;
    const gwh = formatGWh(input.demand.value, locale);
    const tail = rel === null ? "" : `, ${versusLastWeek(rel, locale)}`;
    sentences.push(
      es
        ? `La demanda del ${date} fue de ${gwh} GWh${tail}.`
        : `Demand on ${date} was ${gwh} GWh${tail}.`,
    );
  }

  if (input.price) {
    const value = formatNumber(input.price.value, locale, 0);
    const rel =
      input.price.previous !== null && input.price.previous > 0
        ? ((input.price.value - input.price.previous) / input.price.previous) * 100
        : null;
    const date = formatDate(input.price.day, locale, "short");
    sentences.push(
      es
        ? `El precio de bolsa promedió ${value} COP/kWh el ${date}${rel === null ? "" : ` (${rel >= 0 ? "+" : "−"}${formatNumber(Math.abs(rel), locale, 0)} % en una semana)`}.`
        : `The spot price averaged ${value} COP/kWh on ${date}${rel === null ? "" : ` (${rel >= 0 ? "+" : "−"}${formatNumber(Math.abs(rel), locale, 0)} % in a week)`}.`,
    );
  }

  if (input.reservoir) {
    const level = formatPercent(input.reservoir.value, locale);
    const points = input.reservoir.delta === null ? null : input.reservoir.delta * 100;
    const trend =
      points === null
        ? ""
        : es
          ? ` (${points >= 0 ? "+" : "−"}${formatNumber(Math.abs(points), locale, 1)} puntos en la semana)`
          : ` (${points >= 0 ? "+" : "−"}${formatNumber(Math.abs(points), locale, 1)} points over the week)`;
    sentences.push(es ? `Los embalses están al ${level}${trend}.` : `Reservoirs stand at ${level}${trend}.`);
  }

  if (input.oni) {
    const phase = PHASE[locale][oniPhase(input.oni.value)];
    sentences.push(
      es
        ? `El índice ONI es de ${formatNumber(input.oni.value, locale, 2)}, señal de ${phase}.`
        : `The ONI index is ${formatNumber(input.oni.value, locale, 2)}, a sign of ${phase}.`,
    );
  }

  if (input.mix) {
    const thermal = formatPercent(input.mix.thermal, locale, 0);
    const ago = input.mixYearAgo ? formatPercent(input.mixYearAgo.thermal, locale, 0) : null;
    sentences.push(
      es
        ? `Las térmicas aportaron el ${thermal} de la generación${ago ? `, frente al ${ago} de hace un año` : ""}.`
        : `Thermal plants supplied ${thermal} of generation${ago ? `, against ${ago} a year ago` : ""}.`,
    );
  }

  if (input.demandNextWeek !== null) {
    const gwh = formatGWh(input.demandNextWeek, locale);
    sentences.push(
      es
        ? `El modelo espera una demanda media de ${gwh} GWh por día durante los próximos siete días.`
        : `The model expects average demand of ${gwh} GWh per day over the next seven days.`,
    );
  }

  if (input.priceNextWeek !== null) {
    const value = formatNumber(input.priceNextWeek, locale, 0);
    sentences.push(
      es
        ? `Para el precio, su mediana a siete días es de ${value} COP/kWh, con un rango amplio.`
        : `For price, its seven-day median is ${value} COP/kWh, with a wide range.`,
    );
  }

  return sentences.join(" ");
}

export interface ForecastDescription {
  locale: Locale;
  points: readonly { p10: number; p50: number; p90: number }[];
  scale: number;
  decimals: number;
  unit: string;
}

/** One factual sentence that stands in for the forecast chart (screen readers, no-script). */
export function describeForecast({ locale, points, scale, decimals, unit }: ForecastDescription): string {
  if (points.length === 0) return "";
  const n = (v: number) => formatNumber(v / scale, locale, decimals);
  const medians = points.map((p) => p.p50);
  const mean = medians.reduce((a, b) => a + b, 0) / medians.length;
  const low = Math.min(...points.map((p) => p.p10));
  const high = Math.max(...points.map((p) => p.p90));
  return locale === "es"
    ? `Próximos ${points.length} días: la mediana va de ${n(Math.min(...medians))} a ${n(Math.max(...medians))} ${unit} (promedio ${n(mean)}). El rango del 80 % abarca de ${n(low)} a ${n(high)} ${unit}.`
    : `Next ${points.length} days: the median runs from ${n(Math.min(...medians))} to ${n(Math.max(...medians))} ${unit} (mean ${n(mean)}). The 80 % range spans ${n(low)} to ${n(high)} ${unit}.`;
}

export interface SeriesDescription {
  locale: Locale;
  label: string;
  dates: readonly string[];
  values: readonly (number | null)[];
  scale: number;
  decimals: number;
  unit: string;
}

/** One factual sentence for a historical series: where it started, ended and its extremes. */
export function describeSeries({ locale, label, dates, values, scale, decimals, unit }: SeriesDescription): string {
  let first = -1;
  let last = -1;
  let min = -1;
  let max = -1;
  values.forEach((v, i) => {
    if (v === null || v === undefined) return;
    if (first < 0) first = i;
    last = i;
    if (min < 0 || v < (values[min] as number)) min = i;
    if (max < 0 || v > (values[max] as number)) max = i;
  });
  if (first < 0) return "";
  const n = (i: number) => `${formatNumber((values[i] as number) / scale, locale, decimals)} ${unit}`.trim();
  const d = (i: number) => formatDate(dates[i] as string, locale);
  return locale === "es"
    ? `${label}: de ${n(first)} el ${d(first)} a ${n(last)} el ${d(last)}. Mínimo ${n(min)} el ${d(min)}; máximo ${n(max)} el ${d(max)}.`
    : `${label}: from ${n(first)} on ${d(first)} to ${n(last)} on ${d(last)}. Low ${n(min)} on ${d(min)}; high ${n(max)} on ${d(max)}.`;
}
