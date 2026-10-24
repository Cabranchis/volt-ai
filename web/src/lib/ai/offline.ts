import { getAnomalies, getForecast, getSeries } from "@/lib/data";
import { addDays, formatDate, formatNumber } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import {
  kpi,
  lastDayOf,
  meanOfFirst,
  MIX_SERIES_NAMES,
  mixShares,
} from "@/lib/insights";
import { buildSummary, type SummaryInput } from "@/lib/summary";

type Intent = "price" | "demand" | "hydrology" | "anomalies" | "all";

const KEYWORDS: [Intent, RegExp][] = [
  ["anomalies", /anomal|inusual|unusual|atypical|at[ií]pic|extra[ñn]/i],
  ["price", /precio|price|bolsa|tarifa|costo|cost/i],
  ["hydrology", /embalse|reservoir|hidro|agua|water|ni[ñn]o|\boni\b|clima|climate|lluvia|rain|aporte|inflow/i],
  ["demand", /demanda|demand|consumo|consumption|pron[óo]stico|forecast/i],
];

export function detectIntent(question: string): Intent {
  return KEYWORDS.find(([, pattern]) => pattern.test(question))?.[0] ?? "all";
}

/**
 * Deterministic answer used when no language model is configured or its daily quota is spent.
 * It reuses the same sentences as the overview page, so it can only say what the data says.
 */
export async function answerOffline(question: string, locale: Locale): Promise<string> {
  const intent = detectIntent(question);
  const [frame, demandFc, priceFc] = await Promise.all([
    getSeries(["demand_kwh", "price_mean_cop_kwh", "reservoir_pct", "oni", ...MIX_SERIES_NAMES]),
    getForecast("demand_kwh"),
    getForecast("price_mean_cop_kwh"),
  ]);

  if (intent === "anomalies") {
    const rows = await getAnomalies(5);
    if (rows.length === 0) return locale === "es" ? "Todavía no hay días inusuales registrados." : "No unusual days have been recorded yet.";
    const lines = rows.map((a) => {
      const what = a.target === "demand_kwh" ? (locale === "es" ? "demanda" : "demand") : locale === "es" ? "precio" : "price";
      const dir =
        a.direction === "high"
          ? locale === "es" ? "más alto de lo esperado" : "higher than expected"
          : locale === "es" ? "más bajo de lo esperado" : "lower than expected";
      return `${formatDate(a.day, locale)}: ${what} ${dir} (${locale === "es" ? "severidad" : "severity"} ${formatNumber(a.severity, locale, 1)})`;
    });
    return `${locale === "es" ? "Los días más inusuales son" : "The most unusual days are"}: ${lines.join("; ")}.`;
  }

  const mixDay = lastDayOf(frame, "gen_hydro_kwh");
  const empty: SummaryInput = {
    locale,
    demand: null,
    price: null,
    reservoir: null,
    oni: null,
    mix: null,
    mixYearAgo: null,
    demandNextWeek: null,
    priceNextWeek: null,
  };
  const all: SummaryInput = {
    locale,
    demand: kpi(frame, "demand_kwh"),
    price: kpi(frame, "price_mean_cop_kwh"),
    reservoir: kpi(frame, "reservoir_pct"),
    oni: kpi(frame, "oni", 31),
    mix: mixDay ? mixShares(frame, mixDay) : null,
    mixYearAgo: mixDay ? mixShares(frame, addDays(mixDay, -365)) : null,
    demandNextWeek: demandFc ? meanOfFirst(demandFc.points, 7) : null,
    priceNextWeek: priceFc ? meanOfFirst(priceFc.points, 7) : null,
  };

  const picked: SummaryInput =
    intent === "price"
      ? { ...empty, price: all.price, priceNextWeek: all.priceNextWeek, reservoir: all.reservoir, oni: all.oni }
      : intent === "demand"
        ? { ...empty, demand: all.demand, demandNextWeek: all.demandNextWeek }
        : intent === "hydrology"
          ? { ...empty, reservoir: all.reservoir, oni: all.oni, mix: all.mix, mixYearAgo: all.mixYearAgo }
          : all;

  return buildSummary(picked) || (locale === "es" ? "Todavía no hay datos suficientes para responder." : "There is not enough data yet to answer.");
}
