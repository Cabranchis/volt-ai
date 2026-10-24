import { ArrowDown, ArrowUp } from "lucide-react";
import type { Driver } from "@/lib/data/types";
import { formatSigned } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { featureLabel } from "@/lib/feature-labels";

interface Props {
  locale: Locale;
  drivers: readonly Driver[];
  /** Divide stored contributions by this (1e6 turns kWh into GWh). */
  scale: number;
  decimals: number;
  unit: string;
  color: "demand" | "price";
  dict: Dictionary["drivers"];
}

const BAR_COLOR = { demand: "var(--c-demand)", price: "var(--c-price)" } as const;

/**
 * Factors behind the next forecast, as bars around a zero line: right raises the forecast, left
 * lowers it. Direction is also written as an arrow and a sign, so it never depends on position alone.
 */
export function DriversChart({ locale, drivers, scale, decimals, unit, color, dict }: Props) {
  const max = Math.max(...drivers.map((d) => Math.abs(d.contribution)), Number.EPSILON);

  return (
    <ol className="flex flex-col gap-2.5">
      {drivers.map((driver) => {
        const share = (Math.abs(driver.contribution) / max) * 50;
        const up = driver.direction === "up";
        return (
          <li key={driver.feature} className="grid grid-cols-[minmax(0,1fr)] gap-1 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_5.5rem] sm:items-center sm:gap-4">
            <span className="text-sm">{featureLabel(driver.feature, locale)}</span>
            <span aria-hidden="true" className="relative h-3 rounded-sm bg-surface-2">
              <span className="absolute inset-y-0 left-1/2 w-px bg-line" />
              <span
                className="absolute inset-y-0 rounded-sm"
                style={{
                  background: BAR_COLOR[color],
                  opacity: up ? 1 : 0.5,
                  width: `${share}%`,
                  ...(up ? { left: "50%" } : { right: "50%" }),
                }}
              />
            </span>
            <span className="flex items-center gap-1 text-sm tabular-nums sm:justify-end">
              {up ? (
                <ArrowUp aria-label={dict.up} size={14} strokeWidth={2} />
              ) : (
                <ArrowDown aria-label={dict.down} size={14} strokeWidth={2} />
              )}
              <span className="font-semibold">
                {formatSigned(driver.contribution / scale, locale, decimals)}
              </span>
              <span className="sr-only">{unit}</span>
            </span>
          </li>
        );
      })}
      <li className="text-xs text-faint">{unit}</li>
    </ol>
  );
}

