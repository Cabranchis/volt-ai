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
  /** 24 values, hour 1 to 24, for the latest complete day. */
  latest: (number | null)[];
  /** 24 values: the mean of the previous week at each hour. */
  previousWeek: (number | null)[];
  latestLabel: string;
  weekLabel: string;
  hourLabel: string;
  unit: string;
  ariaLabel: string;
}

const HOURS = Array.from({ length: 24 }, (_, i) => String(i + 1));

export function HourlyChart({ locale, latest, previousWeek, latestLabel, weekLabel, hourLabel, unit, ariaLabel }: Props) {
  const build = useCallback(
    (tokens: ChartTokens, reducedMotion: boolean) => ({
      ...baseOption(tokens, reducedMotion),
      grid: { left: 4, right: 16, top: 26, bottom: 8, containLabel: true },
      tooltip: {
        ...baseOption(tokens, reducedMotion).tooltip,
        formatter: (params: unknown) => {
          const i = (params as { dataIndex: number }[])[0]?.dataIndex ?? 0;
          const fmt = (v: number | null | undefined) =>
            v === null || v === undefined ? "–" : `${formatNumber(v, locale, 0)} ${unit}`;
          return tooltipHtml(tokens, `${hourLabel} ${HOURS[i]}`, [
            { color: tokens.price, label: latestLabel, value: fmt(latest[i]) },
            { color: tokens.ref, label: weekLabel, value: fmt(previousWeek[i]) },
          ]);
        },
      },
      xAxis: {
        type: "category",
        data: HOURS,
        boundaryGap: false,
        axisLine: { lineStyle: { color: tokens.border } },
        axisTick: { show: false },
        axisLabel: { color: tokens.faint, fontSize: 11, interval: 2 },
      },
      yAxis: {
        type: "value",
        name: unit,
        nameTextStyle: { color: tokens.faint, fontSize: 11, align: "left", padding: [0, 0, 0, -4] },
        axisLabel: { color: tokens.faint, fontSize: 11, formatter: (v: number) => formatNumber(v, locale, 0) },
        splitLine: { lineStyle: { color: tokens.border, width: 1 } },
      },
      series: [
        {
          name: weekLabel,
          type: "line",
          data: previousWeek,
          showSymbol: false,
          lineStyle: { width: 2, color: tokens.ref, type: [6, 4] },
          itemStyle: { color: tokens.ref },
          emphasis: { disabled: true },
        },
        {
          name: latestLabel,
          type: "line",
          data: latest,
          showSymbol: false,
          lineStyle: { width: 2, color: tokens.price, cap: "round", join: "round" },
          itemStyle: { color: tokens.price },
          emphasis: { disabled: true },
          z: 3,
        },
      ],
    }),
    [locale, latest, previousWeek, latestLabel, weekLabel, hourLabel, unit],
  );

  return (
    <div className="flex flex-col gap-3">
      <ChartLegend
        items={[
          { label: latestLabel, color: "var(--c-price)", kind: "line" },
          { label: weekLabel, color: "var(--c-ref)", kind: "dashed" },
        ]}
      />
      <EChart build={build} height={260} label={ariaLabel} />
    </div>
  );
}
