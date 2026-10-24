"use client";

import { useMemo, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { RangeControl } from "@/components/ui/RangeControl";
import { formatNumber } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { describeSeries } from "@/lib/summary";
import { ChartLegend } from "./ChartLegend";
import { lastNonNullIndex, rollingMean, spreadMonthly } from "./series-utils";
import { TimeSeriesChart, type SeriesSpec } from "./TimeSeriesChart";

type Range = "1y" | "3y" | "all";
const RANGE_DAYS: Record<Range, number | null> = { "1y": 365, "3y": 1096, all: null };

interface Props {
  locale: Locale;
  dates: string[];
  reservoirPct: (number | null)[];
  inflowsKwh: (number | null)[];
  inflowsHistMeanKwh: (number | null)[];
  oni: (number | null)[];
  priceMean: (number | null)[];
  dict: Dictionary;
}

const GROUP = "hydrology";

export function HydrologyExplorer({
  locale,
  dates,
  reservoirPct,
  inflowsKwh,
  inflowsHistMeanKwh,
  oni,
  priceMean,
  dict,
}: Props) {
  const [range, setRange] = useState<Range>("3y");

  const view = useMemo(() => {
    const smoothed = rollingMean(inflowsKwh, 7);
    const oniDaily = spreadMonthly(dates, oni);
    const last = Math.max(lastNonNullIndex(reservoirPct), lastNonNullIndex(priceMean));
    const days = RANGE_DAYS[range];
    const start = days === null ? 0 : Math.max(0, last - days + 1);
    const cut = <T,>(values: readonly T[]): T[] => values.slice(start, last + 1);
    const oniWindow = cut(oniDaily);
    return {
      dates: cut(dates),
      reservoir: cut(reservoirPct),
      inflows: cut(smoothed),
      inflowsMean: cut(inflowsHistMeanKwh),
      oniUp: oniWindow.map((v) => (v === null ? null : Math.max(v, 0))),
      oniDown: oniWindow.map((v) => (v === null ? null : Math.min(v, 0))),
      oniFull: oniWindow,
      price: cut(priceMean),
    };
  }, [dates, reservoirPct, inflowsKwh, inflowsHistMeanKwh, oni, priceMean, range]);

  const units = dict.units;
  const reservoirSeries: SeriesSpec[] = [
    { name: dict.hydrology.reservoirTitle, values: view.reservoir, color: "water", kind: "area" },
  ];
  const inflowSeries: SeriesSpec[] = [
    { name: dict.hydrology.inflowsAvg, values: view.inflows, color: "water", kind: "area" },
    { name: dict.charts.historicalMean, values: view.inflowsMean, color: "ref", kind: "line", dashed: true },
  ];
  const oniSeries: SeriesSpec[] = [
    { name: dict.kpi.oniNino, values: view.oniUp, color: "nino", kind: "step-area" },
    { name: dict.kpi.oniNina, values: view.oniDown, color: "nina", kind: "step-area" },
  ];
  const priceSeries: SeriesSpec[] = [
    { name: dict.hydrology.priceTitle, values: view.price, color: "price", kind: "line" },
  ];

  const text = (label: string, values: (number | null)[], scale: number, decimals: number, unit: string) =>
    describeSeries({ locale, label, dates: view.dates, values, scale, decimals, unit });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex justify-end">
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

      <Panel title={dict.hydrology.reservoirTitle} note={dict.hydrology.reservoirNote}>
        <TimeSeriesChart
          locale={locale}
          dates={view.dates}
          series={reservoirSeries}
          scale={0.01}
          decimals={0}
          unit={units.percent}
          yMax={1}
          ariaLabel={text(dict.hydrology.reservoirTitle, view.reservoir, 0.01, 0, units.percent)}
          group={GROUP}
        />
        <p className="mt-3 text-sm text-muted">
          {text(dict.hydrology.reservoirTitle, view.reservoir, 0.01, 0, units.percent)}
        </p>
      </Panel>

      <Panel title={dict.hydrology.inflowsTitle} note={dict.hydrology.inflowsNote}>
        <div className="mb-2">
          <ChartLegend
            items={[
              { label: dict.hydrology.inflowsAvg, color: "var(--c-water)", kind: "area" },
              { label: dict.charts.historicalMean, color: "var(--c-ref)", kind: "dashed" },
            ]}
          />
        </div>
        <TimeSeriesChart
          locale={locale}
          dates={view.dates}
          series={inflowSeries}
          scale={1e6}
          decimals={0}
          unit={units.gwhDay}
          yMin={0}
          ariaLabel={text(dict.hydrology.inflowsTitle, view.inflows, 1e6, 0, units.gwhDay)}
          group={GROUP}
        />
        <p className="mt-3 text-sm text-muted">{text(dict.hydrology.inflowsTitle, view.inflows, 1e6, 0, units.gwhDay)}</p>
      </Panel>

      <Panel title={dict.hydrology.oniTitle} note={dict.hydrology.oniNote}>
        <div className="mb-2">
          <ChartLegend
            items={[
              { label: dict.kpi.oniNino, color: "var(--c-nino)", kind: "bar" },
              { label: dict.kpi.oniNina, color: "var(--c-nina)", kind: "bar" },
            ]}
          />
        </div>
        <TimeSeriesChart
          locale={locale}
          dates={view.dates}
          series={oniSeries}
          scale={1}
          decimals={2}
          unit=""
          referenceLines={[
            { value: 0.5, label: formatNumber(0.5, locale, 1) },
            { value: -0.5, label: `−${formatNumber(0.5, locale, 1)}` },
          ]}
          ariaLabel={text(dict.hydrology.oniTitle, view.oniFull, 1, 2, "")}
          group={GROUP}
        />
        <p className="mt-3 text-sm text-muted">{text(dict.hydrology.oniTitle, view.oniFull, 1, 2, "")}</p>
      </Panel>

      <Panel title={dict.hydrology.priceTitle} note={dict.hydrology.priceNote}>
        <TimeSeriesChart
          locale={locale}
          dates={view.dates}
          series={priceSeries}
          scale={1}
          decimals={0}
          unit={units.copKwh}
          yMin={0}
          ariaLabel={text(dict.hydrology.priceTitle, view.price, 1, 0, units.copKwh)}
          group={GROUP}
        />
        <p className="mt-3 text-sm text-muted">{text(dict.hydrology.priceTitle, view.price, 1, 0, units.copKwh)}</p>
      </Panel>
    </div>
  );
}
