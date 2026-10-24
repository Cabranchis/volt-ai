"use client";

import { useCallback } from "react";
import { formatDate, formatNumber } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import { baseOption, monthTickRule, tooltipHtml } from "./chart-utils";
import { EChart } from "./EChart";
import { withAlpha, type ChartTokens } from "./tokens";

export type ColorKey = "demand" | "price" | "water" | "ref" | "nino" | "nina" | "text";

export interface SeriesSpec {
  name: string;
  values: readonly (number | null)[];
  color: ColorKey;
  /** line draws a 2 px line, area adds a ~10 % wash, step holds the value between points. */
  kind: "line" | "area" | "step-area";
  dashed?: boolean;
  /** Not listed in the tooltip (used for helper series). */
  hidden?: boolean;
}

export interface MarkerSpec {
  day: string;
  direction: "high" | "low";
}

interface Props {
  locale: Locale;
  dates: readonly string[];
  series: readonly SeriesSpec[];
  scale: number;
  decimals: number;
  unit: string;
  ariaLabel: string;
  height?: number;
  /** Charts in one group share a cross-hair, so stacked panels read together. */
  group?: string;
  /** Fixed value-axis bounds, e.g. {min: 0}. */
  yMin?: number;
  yMax?: number;
  /** Horizontal reference lines (e.g. the +/-0.5 thresholds of ONI). */
  referenceLines?: { value: number; label: string }[];
  /** Anomaly markers drawn on the first series, as up or down triangles. */
  markers?: readonly MarkerSpec[];
  markerLabels?: { high: string; low: string };
}

const colorOf = (tokens: ChartTokens, key: ColorKey): string => (key === "text" ? tokens.text : tokens[key]);

export function TimeSeriesChart({
  locale,
  dates,
  series,
  scale,
  decimals,
  unit,
  ariaLabel,
  height = 220,
  group,
  yMin,
  yMax,
  referenceLines,
  markers,
  markerLabels,
}: Props) {
  const build = useCallback(
    (tokens: ChartTokens, reducedMotion: boolean) => {
      const span = dates.length;
      const show = (v: number | null | undefined) =>
        v === null || v === undefined ? "–" : formatNumber(v / scale, locale, decimals);
      const dateIndex = new Map(dates.map((d, i) => [d, i]));
      const first = series[0];

      const echartSeries: unknown[] = series.map((spec, n) => {
        const color = colorOf(tokens, spec.color);
        const isArea = spec.kind !== "line";
        return {
          name: spec.name,
          type: "line",
          data: spec.values,
          showSymbol: false,
          step: spec.kind === "step-area" ? "end" : undefined,
          lineStyle: { width: 2, color, type: spec.dashed ? [6, 4] : "solid", cap: "round", join: "round" },
          itemStyle: { color },
          areaStyle: isArea ? { color: withAlpha(color, spec.kind === "step-area" ? 0.45 : 0.12) } : undefined,
          emphasis: { disabled: true },
          z: 2 + n,
          markLine:
            n === 0 && referenceLines?.length
              ? {
                  silent: true,
                  symbol: "none",
                  animation: false,
                  lineStyle: { color: tokens.ref, type: "dashed", width: 1 },
                  label: { color: tokens.muted, fontSize: 11, position: "insideEndTop" },
                  data: referenceLines.map((line) => ({ yAxis: line.value, label: { formatter: line.label } })),
                }
              : undefined,
        };
      });

      if (markers?.length && first) {
        echartSeries.push({
          name: "markers",
          type: "line",
          silent: true,
          lineStyle: { opacity: 0 },
          symbolSize: 11,
          z: 10,
          data: markers
            .map((m) => {
              const i = dateIndex.get(m.day);
              const value = i === undefined ? null : first.values[i];
              if (i === undefined || value === null || value === undefined) return null;
              return {
                value: [i, value],
                symbol: "triangle",
                symbolRotate: m.direction === "low" ? 180 : 0,
                itemStyle: { color: tokens.text, borderColor: tokens.surface, borderWidth: 2 },
              };
            })
            .filter((d) => d !== null),
          // Positions come from the category index, so the series must use the same x axis.
          xAxisIndex: 0,
          yAxisIndex: 0,
          coordinateSystem: "cartesian2d",
        });
      }

      return {
        ...baseOption(tokens, reducedMotion),
        grid: { left: 4, right: 16, top: 26, bottom: 8, containLabel: true },
        tooltip: {
          ...baseOption(tokens, reducedMotion).tooltip,
          formatter: (params: unknown) => {
            const list = params as { dataIndex: number }[];
            const i = list[0]?.dataIndex ?? 0;
            const rows = series
              .filter((s) => !s.hidden)
              .map((s) => ({
                color: colorOf(tokens, s.color),
                label: s.name,
                value: `${show(s.values[i])} ${unit}`.trim(),
              }));
            const marker = markers?.find((m) => m.day === dates[i]);
            if (marker && markerLabels) {
              rows.push({
                color: tokens.text,
                label: marker.direction === "high" ? markerLabels.high : markerLabels.low,
                value: "",
              });
            }
            return tooltipHtml(tokens, formatDate(dates[i] as string, locale, "long"), rows);
          },
        },
        xAxis: {
          type: "category",
          data: dates,
          boundaryGap: false,
          axisLine: { lineStyle: { color: tokens.border } },
          axisTick: { show: false },
          axisLabel: {
            color: tokens.faint,
            fontSize: 11,
            interval: monthTickRule(span),
            formatter: (value: string) => formatDate(value, locale, span > 300 ? "month" : "short"),
          },
        },
        yAxis: {
          type: "value",
          scale: yMin === undefined && yMax === undefined,
          min: yMin,
          max: yMax,
          name: unit,
          nameTextStyle: { color: tokens.faint, fontSize: 11, align: "left", padding: [0, 0, 0, -4] },
          axisLabel: {
            color: tokens.faint,
            fontSize: 11,
            formatter: (v: number) => formatNumber(v / scale, locale, decimals >= 2 ? 1 : 0),
          },
          splitLine: { lineStyle: { color: tokens.border, width: 1 } },
        },
        series: echartSeries,
      };
    },
    [dates, series, scale, decimals, unit, locale, yMin, yMax, referenceLines, markers, markerLabels],
  );

  return <EChart build={build} height={height} label={ariaLabel} group={group} />;
}
