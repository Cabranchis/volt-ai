"use client";

import { useMemo, useState } from "react";
import { DirectionMark } from "@/components/ui/AnomalyList";
import { Panel } from "@/components/ui/Panel";
import { RangeControl } from "@/components/ui/RangeControl";
import { EmptyState } from "@/components/ui/States";
import type { Anomaly, ForecastTarget } from "@/lib/data/types";
import { formatDate, formatGWh, formatNumber } from "@/lib/format";
import { fmt } from "@/lib/i18n/fmt";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { lastNonNullIndex } from "./series-utils";
import { TimeSeriesChart, type SeriesSpec } from "./TimeSeriesChart";

type Range = "1y" | "3y" | "all";
type Order = "recent" | "severity";
/** After this many days without a flagged day the page says so, instead of leaving it to be guessed. */
const QUIET_DAYS = 180;
const RANGE_DAYS: Record<Range, number | null> = { "1y": 365, "3y": 1096, all: null };
const SERIES_KEY = { demand_kwh: "demand", price_mean_cop_kwh: "price" } as const;

interface Props {
  locale: Locale;
  dict: Dictionary;
  dates: string[];
  values: Record<ForecastTarget, (number | null)[]>;
  anomalies: Anomaly[];
}

const num = (value: unknown): number | null => (typeof value === "number" && Number.isFinite(value) ? value : null);

/** "stl_robust_z+isolation_forest" as plain words; a method the dictionary does not know stays as written. */
const methodLabel = (method: string, names: Record<string, string>): string =>
  method
    .split("+")
    .map((part) => names[part] ?? part)
    .join(" + ");

export function AnomaliesExplorer({ locale, dict, dates, values, anomalies }: Props) {
  const [target, setTarget] = useState<ForecastTarget>("demand_kwh");
  const [range, setRange] = useState<Range>("all");
  const [order, setOrder] = useState<Order>("recent");

  const isDemand = target === "demand_kwh";
  const scale = isDemand ? 1e6 : 1;
  const decimals = isDemand ? 1 : 0;
  const unit = isDemand ? dict.units.gwhDay : dict.units.copKwh;

  const view = useMemo(() => {
    const series = values[target];
    const last = lastNonNullIndex(series);
    const days = RANGE_DAYS[range];
    const start = days === null ? 0 : Math.max(0, last - days + 1);
    const viewDates = dates.slice(start, last + 1);
    const first = viewDates[0] ?? "";
    return {
      dates: viewDates,
      values: series.slice(start, last + 1),
      markers: anomalies
        .filter((a) => a.target === target && a.day >= first)
        .map((a) => ({ day: a.day, direction: a.direction })),
    };
  }, [dates, values, target, range, anomalies]);

  const rows = useMemo(
    () =>
      anomalies
        .filter((a) => a.target === target)
        .sort((a, b) => (order === "recent" ? b.day.localeCompare(a.day) : b.severity - a.severity)),
    [anomalies, target, order],
  );

  // The newest flagged day and how long ago it is, whatever the table order is.
  const latest = useMemo(() => {
    const mine = anomalies.filter((a) => a.target === target);
    const newest = mine.reduce<Anomaly | null>((best, a) => (best === null || a.day > best.day ? a : best), null);
    const lastDay = view.dates[view.dates.length - 1];
    const gap = newest && lastDay ? (Date.parse(lastDay) - Date.parse(newest.day)) / 86_400_000 : null;
    return { newest, quiet: gap !== null && gap > QUIET_DAYS };
  }, [anomalies, target, view.dates]);

  const chartSeries: SeriesSpec[] = [
    { name: isDemand ? dict.kpi.demand : dict.kpi.price, values: view.values, color: SERIES_KEY[target], kind: "line" },
  ];
  const show = (value: number | null) =>
    value === null ? "–" : isDemand ? formatGWh(value, locale) : formatNumber(value, locale, 0);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <RangeControl
          label={dict.anomalies.filterLabel}
          value={target}
          onChange={setTarget}
          options={[
            { value: "demand_kwh", label: dict.anomalies.filterDemand },
            { value: "price_mean_cop_kwh", label: dict.anomalies.filterPrice },
          ]}
        />
        <RangeControl
          label={dict.charts.rangeLabel}
          value={range}
          onChange={setRange}
          options={[
            { value: "1y", label: dict.charts.range1y },
            { value: "3y", label: dict.charts.range3y },
            { value: "all", label: dict.charts.rangeAll },
          ]}
        />
      </div>

      <Panel title={dict.anomalies.chartTitle} note={unit}>
        <TimeSeriesChart
          locale={locale}
          dates={view.dates}
          series={chartSeries}
          scale={scale}
          decimals={decimals}
          unit={unit}
          height={320}
          markers={view.markers}
          zoom
          markerLabels={{ high: dict.charts.anomalyHigh, low: dict.charts.anomalyLow }}
          ariaLabel={`${dict.anomalies.chartTitle}: ${view.markers.length}`}
        />
        <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-muted">
          <li className="flex items-center gap-2">
            <DirectionMark direction="high" label={dict.charts.anomalyHigh} />
            {dict.charts.anomalyHigh}
          </li>
          <li className="flex items-center gap-2">
            <DirectionMark direction="low" label={dict.charts.anomalyLow} />
            {dict.charts.anomalyLow}
          </li>
        </ul>
      </Panel>

      <Panel title={order === "recent" ? dict.anomalies.tableCaptionRecent : dict.anomalies.tableCaption}>
        {latest.newest ? (
          <div className="mb-4 flex flex-col gap-2">
            <p className="text-sm">
              {fmt(dict.anomalies.latest, {
                date: formatDate(latest.newest.day, locale, "long"),
                direction: latest.newest.direction === "high" ? dict.anomalies.high : dict.anomalies.low,
                deviation:
                  num(latest.newest.detail?.["deviation_pct"]) === null
                    ? "–"
                    : `${formatNumber(Math.abs(num(latest.newest.detail?.["deviation_pct"]) ?? 0), locale, 1)} %`,
              })}
            </p>
            {latest.quiet ? (
              <p className="max-w-[72ch] text-xs leading-relaxed text-muted">
                {fmt(dict.anomalies.quiet, { date: formatDate(latest.newest.day, locale, "month") })}
              </p>
            ) : null}
          </div>
        ) : null}
        <div className="mb-3">
          <RangeControl
            label={dict.anomalies.sortLabel}
            value={order}
            onChange={setOrder}
            options={[
              { value: "recent", label: dict.anomalies.sortRecent },
              { value: "severity", label: dict.anomalies.sortSeverity },
            ]}
          />
        </div>
        {rows.length === 0 ? (
          <EmptyState title={dict.anomalies.empty} body={dict.common.noDataBody} />
        ) : (
          <div tabIndex={0} role="region" aria-label={dict.anomalies.tableCaption} className="max-h-[28rem] overflow-auto rounded-lg border border-line">
            <table className="w-full min-w-max border-collapse text-sm tabular-nums">
              <caption className="sr-only">{order === "recent" ? dict.anomalies.tableCaptionRecent : dict.anomalies.tableCaption}</caption>
              <thead className="sticky top-0 bg-surface-2 text-xs text-muted">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left font-medium">{dict.common.date}</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">{dict.anomalies.direction}</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">{dict.anomalies.severity}</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">{dict.anomalies.observed} ({unit})</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">{dict.anomalies.expected} ({unit})</th>
                  <th scope="col" className="px-3 py-2 text-left font-medium">{dict.anomalies.method}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => (
                  <tr key={`${a.target}-${a.day}`} className="border-t border-line">
                    <td className="px-3 py-1.5">{formatDate(a.day, locale)}</td>
                    <td className="px-3 py-1.5">
                      <span className="inline-flex items-center gap-2">
                        <DirectionMark direction={a.direction} label={a.direction === "high" ? dict.anomalies.high : dict.anomalies.low} />
                        {a.direction === "high" ? dict.anomalies.high : dict.anomalies.low}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-right font-semibold">{formatNumber(a.severity, locale, 1)}</td>
                    <td className="px-3 py-1.5 text-right">{show(num(a.detail?.["observed"]))}</td>
                    <td className="px-3 py-1.5 text-right">{show(num(a.detail?.["expected"]))}</td>
                    <td className="px-3 py-1.5 text-xs text-muted">{methodLabel(a.method, dict.anomalies.methods)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {rows.length > 0 ? <p className="mt-3 max-w-[72ch] text-xs leading-relaxed text-muted">{dict.anomalies.methodNote}</p> : null}
      </Panel>
    </div>
  );
}
