"use client";

import { CircleAlert, Clock } from "lucide-react";
import { useSyncExternalStore } from "react";
import { daysBetween, formatRelativeDays } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import { fmt } from "@/lib/i18n/fmt";

/** Days after which a forecast counts as old: the pipeline issues one two or three times a day. */
export const FORECAST_OLD_AFTER_DAYS = 2;

interface Props {
  /** ISO timestamp the forecast was issued (the training run that made it). */
  issuedAt: string;
  locale: Locale;
  labels: { issued: string; old: string };
}

const bogotaDay = (date: Date): string => new Intl.DateTimeFormat("en-CA", { timeZone: "America/Bogota" }).format(date);
const subscribe = (): (() => void) => () => {};

/**
 * When the forecast on the page was issued. Pages are cached, so the age is decided in the browser,
 * against today; a forecast the pipeline has not renewed is said to be old instead of looking current.
 */
export function ForecastAge({ issuedAt, locale, labels }: Props) {
  const today = useSyncExternalStore(subscribe, () => bogotaDay(new Date()), () => null);
  const issuedDay = bogotaDay(new Date(issuedAt));
  const age = today === null ? null : daysBetween(issuedDay, today);
  const old = age !== null && age > FORECAST_OLD_AFTER_DAYS;
  const Icon = old ? CircleAlert : Clock;

  return (
    <p
      className={[
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs",
        old ? "border-serious text-serious" : "border-line text-muted",
      ].join(" ")}
    >
      <Icon aria-hidden="true" size={14} strokeWidth={2} />
      <span>
        {fmt(labels.issued, { when: age === null ? issuedDay : formatRelativeDays(age, locale) })}
        {old ? ` · ${fmt(labels.old, { days: age })}` : ""}
      </span>
    </p>
  );
}
