"use client";

import { CircleAlert, CircleCheck } from "lucide-react";
import { useSyncExternalStore } from "react";
import { daysBetween } from "@/lib/format";
import { fmt } from "@/lib/i18n/fmt";

interface Props {
  /** ISO date of the newest value. */
  lastDay: string;
  /** Already formatted date, e.g. "21 Oct 2026". */
  lastDayLabel: string;
  labels: { dataThrough: string; fresh: string; stale: string };
  /** Newer series that the main date does not cover, such as hydrology, already formatted. */
  detail?: string;
  /** Days after which data counts as stale. XM settles demand with a lag of about three days. */
  staleAfterDays?: number;
}

const bogotaToday = (): string =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "America/Bogota" }).format(new Date());

// The calendar day does not change while the page is open, so nothing needs to subscribe.
const subscribe = (): (() => void) => () => {};

/**
 * Pages are cached, so the age of the data cannot be decided on the server.
 * The date is rendered statically; the "stale" state is judged in the browser, against today.
 */
export function Freshness({ lastDay, lastDayLabel, labels, detail, staleAfterDays = 4 }: Props) {
  const today = useSyncExternalStore(subscribe, bogotaToday, () => null);
  const age = today === null ? null : daysBetween(lastDay, today);

  const stale = age !== null && age > staleAfterDays;
  const Icon = stale ? CircleAlert : CircleCheck;

  return (
    <p
      className={[
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs",
        stale ? "border-serious text-serious" : "border-line text-muted",
      ].join(" ")}
    >
      <Icon aria-hidden="true" size={14} strokeWidth={2} className={stale ? "" : "text-good"} />
      <span>
        {fmt(labels.dataThrough, { date: lastDayLabel })}
        {detail ? ` · ${detail}` : ""}
        {stale ? ` · ${fmt(labels.stale, { days: age })}` : ""}
      </span>
    </p>
  );
}
