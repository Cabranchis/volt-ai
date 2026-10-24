import type { Locale } from "./i18n/config";

const tag = (locale: Locale) => (locale === "es" ? "es-CO" : "en-US");

/** Whole-number or fixed-decimal formatting with the locale's separators. */
export function formatNumber(value: number, locale: Locale, decimals = 0): string {
  return new Intl.NumberFormat(tag(locale), {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/** kWh per day to GWh per day: 248 492 454 kWh becomes "248.5". */
export function formatGWh(kwh: number, locale: Locale, decimals = 1): string {
  return formatNumber(kwh / 1e6, locale, decimals);
}

/** A 0..1 fraction as a percentage: 0.761 becomes "76.1 %". */
export function formatPercent(fraction: number, locale: Locale, decimals = 1): string {
  return `${formatNumber(fraction * 100, locale, decimals)} %`;
}

/** Signed difference, e.g. "+3.2" or "-1.4". */
export function formatSigned(value: number, locale: Locale, decimals = 1): string {
  const text = formatNumber(Math.abs(value), locale, decimals);
  if (Number(text.replace(/[^\d]/g, "")) === 0) return text;
  return `${value > 0 ? "+" : "−"}${text}`;
}

/**
 * ISO calendar dates (YYYY-MM-DD) are shown as the same calendar day for everyone,
 * so they are formatted in UTC to avoid shifting by the viewer's time zone.
 */
export function formatDate(
  iso: string,
  locale: Locale,
  style: "short" | "medium" | "long" | "month" = "medium",
): string {
  const date = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  const options: Intl.DateTimeFormatOptions =
    style === "short"
      ? { day: "numeric", month: "short", timeZone: "UTC" }
      : style === "long"
        ? { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }
        : style === "month"
          ? { month: "short", year: "numeric", timeZone: "UTC" }
          : { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" };
  return new Intl.DateTimeFormat(tag(locale), options).format(date);
}

export function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function daysBetween(fromIso: string, toIso: string): number {
  const ms = new Date(`${toIso}T00:00:00Z`).getTime() - new Date(`${fromIso}T00:00:00Z`).getTime();
  return Math.round(ms / 86_400_000);
}

/** "3 days ago", "yesterday", in the viewer's language. */
export function formatRelativeDays(days: number, locale: Locale): string {
  return new Intl.RelativeTimeFormat(tag(locale), { numeric: "auto" }).format(-days, "day");
}
