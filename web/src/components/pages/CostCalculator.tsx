"use client";

import Link from "next/link";
import { useId, useMemo, useState, useSyncExternalStore } from "react";
import { DataTable } from "@/components/ui/DataTable";
import { Panel } from "@/components/ui/Panel";
import { EmptyState } from "@/components/ui/States";
import {
  checkInputs,
  MAX_WINDOW_DAYS,
  parseAmount,
  simulateCost,
  windowDays,
  WINDOW_BACKTEST,
  type InputIssue,
} from "@/lib/cost";
import type { ForecastPoint } from "@/lib/data/types";
import { formatDate, formatNumber, formatPercent } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { fmt } from "@/lib/i18n/fmt";
import { hrefFor } from "@/lib/site";

interface Props {
  locale: Locale;
  dict: Dictionary;
  points: readonly ForecastPoint[];
}

/** Today's date in Colombia, which is the calendar the forecast days follow. */
const bogotaToday = (): string => new Intl.DateTimeFormat("en-CA", { timeZone: "America/Bogota" }).format(new Date());

const subscribeNever = (): (() => void) => () => undefined;

/** Millions of COP, with a decimal for the small amounts. */
const millions = (value: number, locale: Locale): string => formatNumber(value, locale, value < 100 ? 1 : 0);

const field =
  "glass-strong min-h-11 w-full rounded-lg px-3 text-base outline-none tabular-nums placeholder:text-faint focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

/** The cost of buying a volume on the spot market over the next days, with a measured range. */
export function CostCalculator({ locale, dict, points }: Props) {
  const t = dict.calculator;
  const id = useId();
  // The date comes from the visitor's clock; the server renders null, so the first render agrees on both sides.
  const today = useSyncExternalStore(subscribeNever, bogotaToday, () => null);
  const [volume, setVolume] = useState("100");
  const [days, setDays] = useState("7");
  const [contract, setContract] = useState("");

  const available = useMemo(
    () => (today === null ? [] : windowDays(points, today, MAX_WINDOW_DAYS)),
    [points, today],
  );

  const mwh = parseAmount(volume);
  // The forecast can cover fewer days than the choice (a stalled pipeline): never ask for more than exist.
  const nDays = Math.max(1, Math.min(Number(days), available.length));
  const price = contract.trim() === "" ? null : parseAmount(contract);
  const issue: InputIssue | null = available.length === 0 ? null : checkInputs(mwh, nDays, price);

  const result = useMemo(() => {
    if (today === null || issue !== null || available.length === 0) return null;
    return simulateCost({
      points: available.slice(0, nDays),
      mwhPerDay: mwh,
      rho: WINDOW_BACKTEST.rho,
      contractCopKwh: price,
    });
  }, [today, issue, available, nDays, mwh, price]);

  if (today === null) {
    return (
      <Panel title={t.inputsTitle}>
        <p className="text-sm text-muted" role="status">
          {t.loading}
        </p>
      </Panel>
    );
  }
  if (points.length === 0) {
    return (
      <Panel title={t.inputsTitle}>
        <EmptyState title={dict.common.noData} body={t.unavailable} />
      </Panel>
    );
  }
  if (available.length === 0) {
    return (
      <Panel title={t.inputsTitle}>
        <EmptyState title={dict.common.noData} body={t.tooFew} />
      </Panel>
    );
  }

  const errorOf = (key: InputIssue): string | null => (issue === key ? t.errors[key] : null);
  const first = result?.days[0]?.day;
  const last = result?.days.at(-1)?.day;
  const pct = (value: number) => formatPercent(value, locale, 0);

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
      <Panel title={t.inputsTitle}>
        <form className="flex flex-col gap-5" onSubmit={(event) => event.preventDefault()} noValidate>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={`${id}-volume`} className="text-sm font-medium">
              {t.volumeLabel}
            </label>
            <input
              id={`${id}-volume`}
              inputMode="decimal"
              autoComplete="off"
              value={volume}
              onChange={(event) => setVolume(event.target.value)}
              aria-invalid={errorOf("volume") ? true : undefined}
              aria-describedby={`${id}-volume-hint`}
              className={field}
            />
            <p id={`${id}-volume-hint`} className={`text-xs ${errorOf("volume") ? "text-ink" : "text-muted"}`}>
              {errorOf("volume") ?? t.volumeHint}
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor={`${id}-days`} className="text-sm font-medium">
              {t.daysLabel}
            </label>
            <select
              id={`${id}-days`}
              value={String(nDays)}
              onChange={(event) => setDays(event.target.value)}
              aria-describedby={`${id}-days-hint`}
              className={field}
            >
              {available.map((_, index) => (
                <option key={index + 1} value={index + 1}>
                  {index + 1}
                </option>
              ))}
            </select>
            <p id={`${id}-days-hint`} className="text-xs text-muted">
              {errorOf("days") ?? fmt(t.daysHint, { n: available.length })}
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor={`${id}-contract`} className="text-sm font-medium">
              {t.contractLabel}
            </label>
            <input
              id={`${id}-contract`}
              inputMode="decimal"
              autoComplete="off"
              value={contract}
              onChange={(event) => setContract(event.target.value)}
              aria-invalid={errorOf("contract") ? true : undefined}
              aria-describedby={`${id}-contract-hint`}
              className={field}
            />
            <p id={`${id}-contract-hint`} className={`text-xs ${errorOf("contract") ? "text-ink" : "text-muted"}`}>
              {errorOf("contract") ?? t.contractHint}
            </p>
          </div>
        </form>
      </Panel>

      <div className="flex flex-col gap-6">
        {result && first && last ? (
          <>
            <p className="sr-only" role="status" aria-live="polite">
              {t.expected}: {millions(result.cost.p50, locale)} {t.millions}. {t.range}: {millions(result.cost.p10, locale)} – {millions(result.cost.p90, locale)}.
            </p>
            <Panel
              title={t.resultTitle}
              note={
                result.days.length === 1
                  ? fmt(t.resultNoteOne, { mwh: formatNumber(result.totalMwh, locale, 0), from: formatDate(first, locale, "short") })
                  : fmt(t.resultNote, {
                      mwh: formatNumber(result.totalMwh, locale, 0),
                      days: result.days.length,
                      from: formatDate(first, locale, "short"),
                      to: formatDate(last, locale, "short"),
                    })
              }
            >
              <dl className="grid gap-5 sm:grid-cols-3">
                <div className="flex flex-col gap-1">
                  <dt className="order-2 text-sm text-muted">
                    {t.expected} · {t.millions}
                  </dt>
                  <dd className="order-1 text-3xl font-semibold tracking-tight text-accent-ink tabular-nums">
                    {millions(result.cost.p50, locale)}
                  </dd>
                </div>
                <div className="flex flex-col gap-1">
                  <dt className="order-2 text-sm text-muted">
                    {t.range} · {t.millions}
                  </dt>
                  <dd className="order-1 text-3xl font-semibold tracking-tight tabular-nums">
                    {millions(result.cost.p10, locale)} – {millions(result.cost.p90, locale)}
                  </dd>
                </div>
                <div className="flex flex-col gap-1">
                  <dt className="order-2 text-sm text-muted">
                    {t.high} · {t.millions}
                    <span className="mt-0.5 block text-xs text-faint">{t.highNote}</span>
                  </dt>
                  <dd className="order-1 text-3xl font-semibold tracking-tight tabular-nums">
                    {millions(result.cost.p95, locale)}
                  </dd>
                </div>
              </dl>
              <p className="mt-4 text-sm text-muted">
                {t.meanPrice}: {formatNumber(result.meanPrice.p50, locale, 0)} {t.perKwh} (
                {formatNumber(result.meanPrice.p10, locale, 0)} – {formatNumber(result.meanPrice.p90, locale, 0)}).
              </p>
              {result.skipped > 0 ? (
                <p className="mt-2 text-xs text-faint">{fmt(t.skipped, { n: result.skipped })}</p>
              ) : null}
            </Panel>

            {result.contract && price !== null ? (
              <Panel title={t.contractTitle}>
                <ul className="flex flex-col gap-2 text-sm leading-relaxed">
                  <li>
                    {fmt(t.contractCost, {
                      price: formatNumber(price, locale, 0),
                      cost: millions(result.contract.cost, locale),
                    })}
                  </li>
                  <li>{fmt(t.contractProb, { p: pct(result.contract.probSpotHigher) })}</li>
                  <li>
                    {fmt(result.contract.expectedGap >= 0 ? t.contractMore : t.contractLess, {
                      amount: millions(Math.abs(result.contract.expectedGap), locale),
                    })}
                  </li>
                </ul>
              </Panel>
            ) : null}

            <Panel title={t.methodTitle}>
              <p className="max-w-[72ch] text-sm leading-relaxed text-muted">
                {fmt(t.method, {
                  rho: formatNumber(WINDOW_BACKTEST.rho, locale, 1),
                  c3: pct(WINDOW_BACKTEST.coverage[3]),
                  c7: pct(WINDOW_BACKTEST.coverage[7]),
                  c12: pct(WINDOW_BACKTEST.coverage[12]),
                  date: formatDate(WINDOW_BACKTEST.date, locale, "long"),
                  below: `${pct(WINDOW_BACKTEST.belowRange[0])} – ${pct(WINDOW_BACKTEST.belowRange[1])}`,
                  above: `${pct(WINDOW_BACKTEST.aboveRange[0])} – ${pct(WINDOW_BACKTEST.aboveRange[1])}`,
                })}
              </p>
              <p className="mt-3 max-w-[72ch] text-xs leading-relaxed text-faint">{t.caveat}</p>
              <Link
                href={hrefFor(locale, "/models")}
                className="mt-3 inline-block text-sm font-medium text-accent-ink underline underline-offset-4"
              >
                {t.modelsLink}
              </Link>
              <DataTable
                caption={t.tableCaption}
                columns={[
                  { key: "day", header: t.colDay },
                  { key: "price", header: t.colPrice, align: "right" },
                  { key: "median", header: t.colMedian, align: "right" },
                  { key: "cost", header: t.colCost, align: "right" },
                  { key: "range", header: t.colCostRange, align: "right" },
                ]}
                rows={result.days.map((d) => ({
                  day: formatDate(d.day, locale, "long"),
                  price: `${formatNumber(d.p10, locale, 0)} – ${formatNumber(d.p90, locale, 0)}`,
                  median: formatNumber(d.p50, locale, 0),
                  cost: millions(d.costP50, locale),
                  range: `${millions(d.costP10, locale)} – ${millions(d.costP90, locale)}`,
                }))}
                showLabel={dict.common.showTable}
                hideLabel={dict.common.hideTable}
              />
            </Panel>
          </>
        ) : null}
      </div>
    </div>
  );
}
