"use client";

import { useCallback, useMemo, useState } from "react";
import { RangeControl } from "@/components/ui/RangeControl";
import { formatDate, formatNumber } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { baseOption, monthTickRule, tooltipHtml } from "./chart-utils";
import { ChartLegend } from "./ChartLegend";
import { EChart } from "./EChart";
import {
  assembleForecast,
  RANGE_DAYS,
  type ForecastInput,
  type HistoryInput,
  type RangeKey,
} from "./forecast-data";
import { withAlpha, type ChartTokens } from "./tokens";

interface Props {
  locale: Locale;
  history: HistoryInput;
  forecast: readonly ForecastInput[];
  color: "demand" | "price";
  /** Divide stored values by this before showing them (1e6 turns kWh into GWh). */
  scale: number;
  decimals: number;
  unit: string;
  labels: Dictionary["charts"];
  ariaLabel: string;
  defaultRange?: RangeKey;
  /** Hide the range control for compact placements. */
  fixedRange?: boolean;
  height?: number;
}

const LEGEND_COLOR = { demand: "var(--c-demand)", price: "var(--c-price)" } as const;

export function ForecastChart({
  locale,
  history,
  forecast,
  color,
  scale,
  decimals,
  unit,
  labels,
  ariaLabel,
  defaultRange = "1y",
  fixedRange = false,
  height = 340,
}: Props) {
  const [range, setRange] = useState<RangeKey>(defaultRange);
  const assembled = useMemo(
    () => assembleForecast(history, forecast, RANGE_DAYS[range]),
    [history, forecast, range],
  );

  const build = useCallback(
    (tokens: ChartTokens, reducedMotion: boolean) => {
      if (!assembled) return {};
      const seriesColor = tokens[color];
      const show = (v: number | null | undefined) =>
        v === null || v === undefined ? "" : formatNumber(v / scale, locale, decimals);
      const span = assembled.dates.length;
      const upper = assembled.lower.map((low, i) => {
        const w = assembled.width[i];
        return low === null || low === undefined || w === null || w === undefined ? null : low + w;
      });

      return {
        ...baseOption(tokens, reducedMotion),
        grid: { left: 4, right: 16, top: 38, bottom: 8, containLabel: true },
        tooltip: {
          ...baseOption(tokens, reducedMotion).tooltip,
          formatter: (params: unknown) => {
            const list = params as { dataIndex: number }[];
            const i = list[0]?.dataIndex ?? 0;
            const date = assembled.dates[i] as string;
            const isForecast = i > assembled.lastObservedIndex;
            const rows = isForecast
              ? [
                  { color: seriesColor, label: labels.forecast, value: `${show(assembled.median[i])} ${unit}` },
                  {
                    color: null,
                    label: labels.band,
                    value: `${show(assembled.lower[i])} – ${show((assembled.lower[i] ?? 0) + (assembled.width[i] ?? 0))}`,
                    muted: true,
                  },
                ]
              : [{ color: seriesColor, label: labels.observed, value: `${show(assembled.observed[i])} ${unit}` }];
            return tooltipHtml(tokens, formatDate(date, locale, "long"), rows);
          },
        },
        xAxis: {
          type: "category",
          data: assembled.dates,
          boundaryGap: false,
          axisLine: { lineStyle: { color: tokens.border } },
          axisTick: { show: false },
          axisLabel: {
            color: tokens.faint,
            fontSize: 11,
            interval: monthTickRule(span),
            hideOverlap: true,
            formatter: (value: string) => formatDate(value, locale, span > 300 ? "month" : "short"),
          },
        },
        yAxis: {
          type: "value",
          scale: true,
          name: unit,
          nameTextStyle: { color: tokens.faint, fontSize: 11, align: "left", padding: [0, 0, 0, -4] },
          axisLabel: { color: tokens.faint, fontSize: 11, formatter: (v: number) => formatNumber(v / scale, locale, 0) },
          splitLine: { lineStyle: { color: tokens.border, width: 1 } },
        },
        series: [
          {
            name: labels.observed,
            type: "line",
            data: assembled.observed,
            showSymbol: false,
            lineStyle: { width: 2, color: seriesColor, cap: "round", join: "round" },
            itemStyle: { color: seriesColor },
            emphasis: { disabled: true },
            z: 3,
            markLine: {
              silent: true,
              symbol: "none",
              animation: false,
              lineStyle: { color: tokens.ref, type: "dashed", width: 1 },
              label: { formatter: labels.lastObserved, color: tokens.muted, fontSize: 11, position: "end", rotate: 0, distance: 8, align: "right" },
              data: [{ xAxis: assembled.lastObservedIndex }],
            },
          },
          {
            // Invisible base of the band: everything below P10.
            name: "band-base",
            type: "line",
            data: assembled.lower,
            stack: "band",
            showSymbol: false,
            silent: true,
            lineStyle: { width: 1, color: withAlpha(seriesColor, 0.5) },
            areaStyle: { opacity: 0 },
            tooltip: { show: false },
            z: 1,
          },
          {
            // Upper edge of the band, drawn as a hairline so the interval reads as a shape.
            name: "band-upper",
            type: "line",
            data: upper,
            showSymbol: false,
            silent: true,
            lineStyle: { width: 1, color: withAlpha(seriesColor, 0.5) },
            tooltip: { show: false },
            z: 1,
          },
          {
            name: labels.band,
            type: "line",
            data: assembled.width,
            stack: "band",
            showSymbol: false,
            silent: true,
            lineStyle: { opacity: 0 },
            areaStyle: { color: withAlpha(seriesColor, 0.24) },
            z: 1,
          },
          {
            name: labels.forecast,
            type: "line",
            data: assembled.median,
            showSymbol: false,
            lineStyle: { width: 2, color: seriesColor, type: [6, 4], cap: "round" },
            itemStyle: { color: seriesColor },
            emphasis: { disabled: true },
            z: 2,
          },
        ],
      };
    },
    [assembled, color, labels, locale, scale, decimals, unit],
  );

  if (!assembled) return null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ChartLegend
          items={[
            { label: labels.observed, color: LEGEND_COLOR[color], kind: "line" },
            { label: labels.forecast, color: LEGEND_COLOR[color], kind: "dashed" },
            { label: labels.band, color: LEGEND_COLOR[color], kind: "area" },
          ]}
        />
        {fixedRange ? null : (
          <RangeControl
            label={labels.rangeLabel}
            value={range}
            onChange={setRange}
            options={[
              { value: "3m", label: labels.range3m },
              { value: "1y", label: labels.range1y },
              { value: "3y", label: labels.range3y },
              { value: "all", label: labels.rangeAll },
            ]}
          />
        )}
      </div>
      <EChart build={build} height={height} label={ariaLabel} />
    </div>
  );
}
