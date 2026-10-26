import type { ChartTokens } from "./tokens";

export interface TooltipRow {
  /** CSS colour for the key dot, or null for a plain row. */
  color: string | null;
  label: string;
  value: string;
  /** Rows can be dimmed (e.g. an interval) so the headline value reads first. */
  muted?: boolean;
}

const escapeHtml = (text: string): string =>
  text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);

/** HTML for an ECharts tooltip, styled from the tokens. All text is escaped. */
export function tooltipHtml(tokens: ChartTokens, title: string, rows: readonly TooltipRow[]): string {
  const body = rows
    .map((row) => {
      const dot = row.color
        ? `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${row.color};margin-right:8px"></span>`
        : `<span style="display:inline-block;width:16px"></span>`;
      const colour = row.muted ? tokens.muted : tokens.text;
      return `<div style="display:flex;justify-content:space-between;gap:20px;color:${colour}"><span>${dot}${escapeHtml(row.label)}</span><span style="font-variant-numeric:tabular-nums;font-weight:600">${escapeHtml(row.value)}</span></div>`;
    })
    .join("");
  return `<div style="font-size:12px;line-height:1.6;min-width:180px"><div style="color:${tokens.muted};margin-bottom:4px">${escapeHtml(title)}</div>${body}</div>`;
}

/** Base look shared by every chart: tooltip surface, hairline grid, quiet axes. */
export function baseOption(tokens: ChartTokens, reducedMotion: boolean) {
  return {
    animation: !reducedMotion,
    animationDuration: 700,
    animationEasing: "cubicOut" as const,
    animationDurationUpdate: reducedMotion ? 0 : 200,
    textStyle: { fontFamily: tokens.font, color: tokens.muted },
    tooltip: {
      trigger: "axis" as const,
      confine: true,
      backgroundColor: tokens.surface,
      borderColor: tokens.border,
      borderWidth: 1,
      padding: [10, 12],
      textStyle: { color: tokens.text, fontFamily: tokens.font, fontSize: 12 },
      extraCssText: "border-radius:10px;box-shadow:0 6px 20px rgba(0,0,0,0.12);",
      axisPointer: {
        type: "line" as const,
        lineStyle: { color: tokens.faint, width: 1, type: "solid" as const },
      },
    },
  };
}

/**
 * Axis label tick rule: which category labels to draw, by the span being shown.
 * Labels are about 65 px wide, so the density follows the span to keep them from touching.
 */
export function monthTickRule(spanDays: number): (index: number, value: string) => boolean {
  if (spanDays <= 120) return (_i, value) => value.endsWith("-01") || value.endsWith("-15");
  if (spanDays <= 270) return (_i, value) => value.endsWith("-01");
  if (spanDays <= 800) return (_i, value) => value.endsWith("-01") && ["01", "04", "07", "10"].includes(value.slice(5, 7));
  if (spanDays <= 1500) return (_i, value) => value.endsWith("-01-01") || value.endsWith("-07-01");
  return (_i, value) => value.endsWith("-01-01");
}

/**
 * Label rule for a zoomed window of `visible` days starting at index `start`: the usual rule for
 * long windows, and about six evenly spaced labels for short ones, which may hold no month start.
 */
export function zoomTickRule(start: number, visible: number): (index: number, value: string) => boolean {
  if (visible > 45) return monthTickRule(visible);
  const every = Math.max(1, Math.round(visible / 6));
  return (index) => (index - start) % every === 0;
}

export function compactNumber(value: number, locale: string): string {
  return new Intl.NumberFormat(locale === "es" ? "es-CO" : "en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}
