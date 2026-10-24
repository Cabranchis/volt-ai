"use client";

import { useCallback } from "react";
import { formatDate, formatPercent } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { MIX_ORDER, type MixKey } from "@/lib/insights";
import { baseOption, tooltipHtml } from "./chart-utils";
import { ChartLegend } from "./ChartLegend";
import { EChart } from "./EChart";
import type { ChartTokens } from "./tokens";

interface Props {
  locale: Locale;
  /** "YYYY-MM" for each point. */
  months: string[];
  shares: Record<MixKey, number[]>;
  labels: Dictionary["mix"];
  ariaLabel: string;
  height?: number;
}

const TOKEN_OF: Record<MixKey, keyof ChartTokens> = {
  thermal: "thermal",
  hydro: "water",
  wind: "wind",
  solar: "solar",
  cogen: "cogen",
  other: "other",
};
const CSS_OF: Record<MixKey, string> = {
  thermal: "var(--c-thermal)",
  hydro: "var(--c-water)",
  wind: "var(--c-wind)",
  solar: "var(--c-solar)",
  cogen: "var(--c-cogen)",
  other: "var(--c-other)",
};

export function MixAreaChart({ locale, months, shares, labels, ariaLabel, height = 300 }: Props) {
  const build = useCallback(
    (tokens: ChartTokens, reducedMotion: boolean) => ({
      ...baseOption(tokens, reducedMotion),
      grid: { left: 4, right: 16, top: 12, bottom: 8, containLabel: true },
      tooltip: {
        ...baseOption(tokens, reducedMotion).tooltip,
        formatter: (params: unknown) => {
          const i = (params as { dataIndex: number }[])[0]?.dataIndex ?? 0;
          const rows = [...MIX_ORDER]
            .reverse()
            .map((key) => ({
              color: tokens[TOKEN_OF[key]] as string,
              label: labels[key],
              value: formatPercent(shares[key][i] ?? 0, locale, 1),
            }));
          return tooltipHtml(tokens, formatDate(`${months[i]}-01`, locale, "month"), rows);
        },
      },
      xAxis: {
        type: "category",
        data: months,
        boundaryGap: false,
        axisLine: { lineStyle: { color: tokens.border } },
        axisTick: { show: false },
        axisLabel: {
          color: tokens.faint,
          fontSize: 11,
          interval: (_i: number, value: string) => value.endsWith("-01"),
          formatter: (value: string) => formatDate(`${value}-01`, locale, "month"),
        },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 1,
        axisLabel: { color: tokens.faint, fontSize: 11, formatter: (v: number) => formatPercent(v, locale, 0) },
        splitLine: { lineStyle: { color: tokens.border, width: 1 } },
      },
      series: MIX_ORDER.map((key) => ({
        name: labels[key],
        type: "line",
        stack: "mix",
        data: shares[key],
        showSymbol: false,
        // The 2 px surface-coloured edge is the gap between stacked areas.
        lineStyle: { width: 2, color: tokens.surface },
        areaStyle: { color: tokens[TOKEN_OF[key]] as string, opacity: 1 },
        itemStyle: { color: tokens[TOKEN_OF[key]] as string },
        emphasis: { disabled: true },
      })),
    }),
    [locale, months, shares, labels],
  );

  return (
    <div className="flex flex-col gap-3">
      <ChartLegend items={MIX_ORDER.map((key) => ({ label: labels[key], color: CSS_OF[key], kind: "bar" as const }))} />
      <EChart build={build} height={height} label={ariaLabel} />
    </div>
  );
}
