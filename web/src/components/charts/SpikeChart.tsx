"use client";

import { useCallback } from "react";
import { formatDate, formatPercent } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import type { SpikeDay } from "@/lib/spikes";
import { baseOption, tooltipHtml } from "./chart-utils";
import { ChartLegend } from "./ChartLegend";
import { EChart } from "./EChart";
import type { ChartTokens } from "./tokens";

interface Props {
  locale: Locale;
  days: readonly SpikeDay[];
  labels: { aboveLevel: string; rise: string; dayAhead: string };
  ariaLabel: string;
}

/** Probability of each event on each forecast day: two lines on a 0 to 100 % axis. */
export function SpikeChart({ locale, days, labels, ariaLabel }: Props) {
  const build = useCallback(
    (tokens: ChartTokens, reducedMotion: boolean) => ({
      ...baseOption(tokens, reducedMotion),
      grid: { left: 4, right: 16, top: 16, bottom: 24, containLabel: true },
      tooltip: {
        ...baseOption(tokens, reducedMotion).tooltip,
        formatter: (params: unknown) => {
          const i = (params as { dataIndex: number }[])[0]?.dataIndex ?? 0;
          const d = days[i];
          if (!d) return "";
          return tooltipHtml(tokens, `${formatDate(d.day, locale, "long")} · ${labels.dayAhead} ${d.horizon}`, [
            { color: tokens.price, label: labels.aboveLevel, value: formatPercent(d.aboveLevel, locale, 0) },
            { color: tokens.ref, label: labels.rise, value: formatPercent(d.rise, locale, 0) },
          ]);
        },
      },
      xAxis: {
        type: "category",
        data: days.map((d) => d.horizon),
        boundaryGap: false,
        name: labels.dayAhead,
        nameLocation: "middle",
        nameGap: 26,
        nameTextStyle: { color: tokens.faint, fontSize: 11 },
        axisLine: { lineStyle: { color: tokens.border } },
        axisTick: { show: false },
        axisLabel: { color: tokens.faint, fontSize: 11 },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 1,
        interval: 0.25,
        axisLabel: { color: tokens.faint, fontSize: 11, formatter: (v: number) => formatPercent(v, locale, 0) },
        splitLine: { lineStyle: { color: tokens.border, width: 1 } },
      },
      series: [
        {
          name: labels.rise,
          type: "line",
          data: days.map((d) => d.rise),
          showSymbol: false,
          emphasis: { disabled: true },
          lineStyle: { width: 2, color: tokens.ref, type: [6, 4] },
          itemStyle: { color: tokens.ref },
        },
        {
          name: labels.aboveLevel,
          type: "line",
          data: days.map((d) => d.aboveLevel),
          showSymbol: false,
          emphasis: { disabled: true },
          z: 3,
          lineStyle: { width: 2, color: tokens.price, cap: "round", join: "round" },
          itemStyle: { color: tokens.price },
          areaStyle: { color: tokens.price, opacity: 0.1 },
        },
      ],
    }),
    [locale, days, labels],
  );

  return (
    <div className="flex flex-col gap-3">
      <ChartLegend
        items={[
          { label: labels.aboveLevel, color: "var(--c-price)", kind: "line" },
          { label: labels.rise, color: "var(--c-ref)", kind: "dashed" },
        ]}
      />
      <EChart build={build} height={240} label={ariaLabel} />
    </div>
  );
}
