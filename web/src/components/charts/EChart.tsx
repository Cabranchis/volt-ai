"use client";

import { useEffect, useRef } from "react";
import { echarts, type EChartsCoreOption } from "./echarts-setup";
import { readTokens, type ChartTokens } from "./tokens";

interface Props {
  /** Builds the option from the current theme tokens. Called again when the theme changes. */
  build: (tokens: ChartTokens, reducedMotion: boolean) => EChartsCoreOption;
  height: number;
  /** Text read by assistive technology; a full text summary and a table sit beside every chart. */
  label: string;
  /** Charts that share a group get linked tooltips and cross-hairs. */
  group?: string;
  /** Called once the chart exists, to attach events; the function it returns runs on teardown. */
  onChart?: (chart: ReturnType<typeof echarts.init>) => void | (() => void);
}

/**
 * Thin, theme-aware wrapper around an ECharts canvas.
 * It never owns data: callers pass a `build` function, so this stays reusable and testable.
 */
export function EChart({ build, height, label, group, onChart }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof echarts.init> | null>(null);
  const buildRef = useRef(build);
  const onChartRef = useRef(onChart);

  useEffect(() => {
    buildRef.current = build;
    onChartRef.current = onChart;
    const chart = chartRef.current;
    if (chart) {
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      chart.setOption(buildRef.current(readTokens(), reduced), { notMerge: true });
    }
  }, [build, onChart]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    let chart: ReturnType<typeof echarts.init>;
    try {
      chart = echarts.init(element, undefined, { renderer: "canvas" });
    } catch {
      // No canvas (very old browser, blocked context): the text summary and the table remain.
      return;
    }
    chartRef.current = chart;
    if (group) {
      chart.group = group;
      echarts.connect(group);
    }

    const render = () => {
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      chart.setOption(buildRef.current(readTokens(), reduced), { notMerge: true });
    };
    render();
    const detach = onChartRef.current?.(chart);

    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(element);

    // Re-theme when the visitor switches theme or the OS preference changes.
    const themeObserver = new MutationObserver(render);
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", render);

    return () => {
      detach?.();
      resizeObserver.disconnect();
      themeObserver.disconnect();
      media.removeEventListener("change", render);
      chart.dispose();
      chartRef.current = null;
    };
  }, [group]);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label={label}
      style={{ height }}
      className="w-full"
    />
  );
}
