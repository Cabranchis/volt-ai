import type { Stat } from "@/components/ui/StatStrip";
import { formatDate, formatGWh, formatNumber, formatPercent, formatSigned } from "./format";
import type { Locale } from "./i18n/config";
import type { Dictionary } from "./i18n/en";
import { fmt } from "./i18n/fmt";
import { oniPhase, type Kpi } from "./insights";

/**
 * The headline tiles shared by the overview and the hydrology page. Each tile keeps its own date,
 * because XM settles demand, price and hydrology on different days.
 */
const sign = (delta: number | null): -1 | 0 | 1 => (delta === null ? 0 : (Math.sign(delta) as -1 | 0 | 1));

export function demandStat(k: Kpi, locale: Locale, dict: Dictionary): Stat {
  return {
    label: dict.kpi.demand,
    value: formatGWh(k.value, locale),
    unit: dict.units.gwhDay,
    delta:
      k.delta === null
        ? undefined
        : fmt(dict.kpi.vsWeek, { delta: formatSigned(k.delta / 1e6, locale), unit: dict.units.gwhDay }),
    deltaSign: sign(k.delta),
    context: fmt(dict.kpi.onDate, { date: formatDate(k.day, locale) }),
  };
}

export function priceStat(k: Kpi, locale: Locale, dict: Dictionary): Stat {
  return {
    label: dict.kpi.price,
    value: formatNumber(k.value, locale, 0),
    unit: dict.units.copKwh,
    delta:
      k.delta === null
        ? undefined
        : fmt(dict.kpi.vsWeek, { delta: formatSigned(k.delta, locale, 0), unit: dict.units.copKwh }),
    deltaSign: sign(k.delta),
    context: fmt(dict.kpi.onDate, { date: formatDate(k.day, locale) }),
  };
}

export function reservoirStat(k: Kpi, locale: Locale, dict: Dictionary): Stat {
  return {
    label: dict.kpi.reservoir,
    value: formatPercent(k.value, locale).replace(" %", ""),
    unit: dict.units.percent,
    delta:
      k.delta === null ? undefined : fmt(dict.kpi.vsWeekPoints, { delta: formatSigned(k.delta * 100, locale) }),
    deltaSign: sign(k.delta),
    context: fmt(dict.kpi.onDate, { date: formatDate(k.day, locale) }),
  };
}

export function oniStat(k: Kpi, locale: Locale, dict: Dictionary): Stat {
  const phase = {
    strongNino: dict.kpi.oniStrongNino,
    nino: dict.kpi.oniNino,
    neutral: dict.kpi.oniNeutral,
    nina: dict.kpi.oniNina,
  }[oniPhase(k.value)];
  return {
    label: dict.kpi.oni,
    value: formatNumber(k.value, locale, 2),
    unit: "",
    note: phase,
    context: fmt(dict.kpi.oniSeason, { month: formatDate(k.day, locale, "month") }),
  };
}

/** River inflows as a share of the historical mean for the same day: 100 % is a normal day. */
export function inflowsStat(inflows: Kpi, historicalMean: number, locale: Locale, dict: Dictionary): Stat | null {
  if (!(historicalMean > 0)) return null;
  const ratio = inflows.value / historicalMean;
  return {
    label: dict.kpi.inflows,
    value: formatNumber(ratio * 100, locale, 0),
    unit: dict.units.percent,
    note: fmt(dict.kpi.inflowsNote, { gwh: formatGWh(inflows.value, locale) }),
    context: fmt(dict.kpi.onDate, { date: formatDate(inflows.day, locale) }),
  };
}
