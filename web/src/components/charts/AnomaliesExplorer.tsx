"use client";

import { useMemo, useState } from "react";
import { DirectionMark } from "@/components/ui/AnomalyList";
import { Panel } from "@/components/ui/Panel";
import { RangeControl } from "@/components/ui/RangeControl";
import { EmptyState } from "@/components/ui/States";
import type { Anomaly, ForecastTarget } from "@/lib/data/types";
import { formatDate, formatGWh, formatNumber } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { lastNonNullIndex } from "./series-utils";
import { TimeSeriesChart, type SeriesSpec } from "./TimeSeriesChart";

type Range = "1y" | "3y" | "all";
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
    () => anomalies.filter((a) => a.target === target).sort((a, b) => b.severity - a.severity),
    [anomalies, target],
  );

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

      <Panel title={dict.anomalies.tableCaption}>
        {rows.length === 0 ? (
          <EmptyState title={dict.anomalies.empty} body={dict.common.noDataBody} />
        ) : (
          <div tabIndex={0} role="region" aria-label={dict.anomalies.tableCaption} className="max-h-[28rem] overflow-auto rounded-lg border border-line">
            <table className="w-full min-w-max border-collapse text-sm tabular-nums">
              <caption className="sr-only">{dict.anomalies.tableCaption}</caption>
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
