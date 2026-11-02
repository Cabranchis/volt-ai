"use client";

import { useCallback, useMemo } from "react";
import { buildCaseSeries, type CasePoint } from "@/lib/case-study/el-nino";
import { formatDate, formatNumber } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { baseOption, tooltipHtml, type TooltipRow } from "./chart-utils";
import { ChartLegend } from "./ChartLegend";
import { EChart } from "./EChart";
import { withAlpha, type ChartTokens } from "./tokens";

interface Props {
  locale: Locale;
  point: CasePoint;
  labels: Dictionary["caseStudy"]["chart"];
  ariaLabel: string;
  height?: number;
}

/** One forecast origin: what was known, what the model said (median and 80 % band), what happened. */
export function CaseChart({ locale, point, labels, ariaLabel, height = 300 }: Props) {
  const series = useMemo(() => buildCaseSeries(point), [point]);

  const build = useCallback(
    (tokens: ChartTokens, reducedMotion: boolean) => {
      const color = tokens.price;
      const show = (v: number | null | undefined) => (v === null || v === undefined ? "–" : formatNumber(v, locale, 0));
      const upper = series.lower.map((low, i) => {
        const w = series.width[i];
        return low === null || low === undefined || w === null || w === undefined ? null : low + w;
      });
      const base = baseOption(tokens, reducedMotion);
      return {
        ...base,
        grid: { left: 4, right: 16, top: 30, bottom: 8, containLabel: true },
        tooltip: {
          ...base.tooltip,
          formatter: (params: unknown) => {
            const i = (params as { dataIndex: number }[])[0]?.dataIndex ?? 0;
            const ahead = i > series.originIndex;
            const rows: TooltipRow[] = [{ color, label: labels.actual, value: `${show(series.observed[i])} ${labels.unit}` }];
            if (ahead) {
              rows.push(
                { color, label: labels.median, value: `${show(series.median[i])} ${labels.unit}` },
                {
                  color: null,
                  label: labels.band,
                  value: `${show(series.lower[i])} – ${show(upper[i])}`,
                },
                { color: tokens.faint, label: labels.ets, value: `${show(series.ets[i])} ${labels.unit}` },
              );
            }
            return tooltipHtml(tokens, formatDate(series.dates[i] as string, locale, "long"), rows);
          },
        },
        xAxis: {
          type: "category",
          data: series.dates,
          boundaryGap: false,
          axisLine: { lineStyle: { color: tokens.border } },
          axisTick: { show: false },
          axisLabel: {
            color: tokens.faint,
            fontSize: 11,
            hideOverlap: true,
            interval: (i: number) => i % 7 === 0,
            formatter: (value: string) => formatDate(value, locale, "short"),
          },
        },
        yAxis: {
          type: "value",
          min: 0,
          name: labels.unit,
          nameTextStyle: { color: tokens.faint, fontSize: 11, align: "left", padding: [0, 0, 0, -4] },
          axisLabel: { color: tokens.faint, fontSize: 11, formatter: (v: number) => formatNumber(v, locale, 0) },
          splitLine: { lineStyle: { color: tokens.border, width: 1 } },
        },
        series: [
          {
            name: labels.actual,
            type: "line",
            data: series.observed,
            showSymbol: false,
            lineStyle: { width: 2.5, color, cap: "round", join: "round" },
            itemStyle: { color },
            emphasis: { disabled: true },
            z: 4,
            markLine: {
              silent: true,
              symbol: "none",
              animation: false,
              lineStyle: { color: tokens.ref, type: "dashed", width: 1 },
              label: { formatter: labels.origin, color: tokens.muted, fontSize: 11, position: "end", rotate: 0, distance: 8, align: "right" },
              data: [{ xAxis: series.originIndex }],
            },
          },
          {
            name: "band-base",
            type: "line",
            data: series.lower,
            stack: "band",
            showSymbol: false,
            silent: true,
            lineStyle: { width: 1, color: withAlpha(color, 0.5) },
            areaStyle: { opacity: 0 },
            tooltip: { show: false },
            z: 1,
          },
          {
            name: "band-upper",
            type: "line",
            data: upper,
            showSymbol: false,
            silent: true,
            lineStyle: { width: 1, color: withAlpha(color, 0.5) },
            tooltip: { show: false },
            z: 1,
          },
          {
            name: labels.band,
            type: "line",
            data: series.width,
            stack: "band",
            showSymbol: false,
            silent: true,
            lineStyle: { opacity: 0 },
            areaStyle: { color: withAlpha(color, 0.22) },
            z: 1,
          },
          {
            name: labels.median,
            type: "line",
            data: series.median,
            showSymbol: false,
            lineStyle: { width: 2, color, type: [6, 4], cap: "round" },
            itemStyle: { color },
            emphasis: { disabled: true },
            z: 3,
          },
          {
            name: labels.ets,
            type: "line",
            data: series.ets,
            showSymbol: false,
            lineStyle: { width: 1.5, color: tokens.faint, type: [2, 3] },
            itemStyle: { color: tokens.faint },
            emphasis: { disabled: true },
            z: 2,
          },
        ],
      };
    },
    [series, labels, locale],
  );

  return (
    <div className="flex flex-col gap-3">
      <ChartLegend
        items={[
          { label: labels.actual, color: "var(--c-price)", kind: "line" },
          { label: labels.median, color: "var(--c-price)", kind: "dashed" },
          { label: labels.band, color: "var(--c-price)", kind: "area" },
          { label: labels.ets, color: "var(--text-faint)", kind: "dotted" },
        ]}
      />
      <EChart build={build} height={height} label={ariaLabel} />
    </div>
  );
}
