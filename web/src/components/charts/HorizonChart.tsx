"use client";

import { useCallback } from "react";
import { formatNumber } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import { baseOption, tooltipHtml } from "./chart-utils";
import { ChartLegend } from "./ChartLegend";
import { EChart } from "./EChart";
import type { ChartTokens } from "./tokens";

interface Props {
  locale: Locale;
  days: number[];
  model: (number | null)[];
  seasonalNaive: (number | null)[];
  ets: (number | null)[];
  labels: { model: string; seasonalNaive: string; ets: string; dayAhead: string };
  color: "demand" | "price";
  ariaLabel: string;
}

const CSS = { demand: "var(--c-demand)", price: "var(--c-price)" } as const;

/** Backtest error by days ahead, for the model and both baselines. */
export function HorizonChart({ locale, days, model, seasonalNaive, ets, labels, color, ariaLabel }: Props) {
  const build = useCallback(
    (tokens: ChartTokens, reducedMotion: boolean) => ({
      ...baseOption(tokens, reducedMotion),
      grid: { left: 4, right: 16, top: 26, bottom: 24, containLabel: true },
      tooltip: {
        ...baseOption(tokens, reducedMotion).tooltip,
        formatter: (params: unknown) => {
          const i = (params as { dataIndex: number }[])[0]?.dataIndex ?? 0;
          const fmt = (v: number | null | undefined) => (v === null || v === undefined ? "–" : formatNumber(v, locale, 2));
          return tooltipHtml(tokens, `${labels.dayAhead}: ${days[i]}`, [
            { color: tokens[color], label: labels.model, value: fmt(model[i]) },
            { color: tokens.ref, label: labels.seasonalNaive, value: fmt(seasonalNaive[i]) },
            { color: tokens.text, label: labels.ets, value: fmt(ets[i]) },
          ]);
        },
      },
      xAxis: {
        type: "category",
        data: days.map(String),
        boundaryGap: false,
        name: labels.dayAhead,
        nameLocation: "middle",
        nameGap: 26,
        nameTextStyle: { color: tokens.faint, fontSize: 11 },
        axisLine: { lineStyle: { color: tokens.border } },
        axisTick: { show: false },
        axisLabel: { color: tokens.faint, fontSize: 11, interval: (i: number) => i === 0 || (i + 1) % 5 === 0 },
      },
      yAxis: {
        type: "value",
        name: "MASE",
        min: 0,
        nameTextStyle: { color: tokens.faint, fontSize: 11, align: "left", padding: [0, 0, 0, -4] },
        axisLabel: { color: tokens.faint, fontSize: 11, formatter: (v: number) => formatNumber(v, locale, 1) },
        splitLine: { lineStyle: { color: tokens.border, width: 1 } },
      },
      series: [
        { name: labels.seasonalNaive, type: "line", data: seasonalNaive, showSymbol: false, emphasis: { disabled: true }, lineStyle: { width: 2, color: tokens.ref, type: [6, 4] }, itemStyle: { color: tokens.ref } },
        { name: labels.ets, type: "line", data: ets, showSymbol: false, emphasis: { disabled: true }, lineStyle: { width: 2, color: tokens.text, type: [2, 3] }, itemStyle: { color: tokens.text } },
        { name: labels.model, type: "line", data: model, showSymbol: false, emphasis: { disabled: true }, z: 3, lineStyle: { width: 2, color: tokens[color], cap: "round", join: "round" }, itemStyle: { color: tokens[color] } },
      ],
    }),
    [locale, days, model, seasonalNaive, ets, labels, color],
  );

  return (
    <div className="flex flex-col gap-3">
      <ChartLegend
        items={[
          { label: labels.model, color: CSS[color], kind: "line" },
          { label: labels.seasonalNaive, color: "var(--c-ref)", kind: "dashed" },
          { label: labels.ets, color: "var(--text)", kind: "dashed" },
        ]}
      />
      <EChart build={build} height={260} label={ariaLabel} />
    </div>
  );
}
