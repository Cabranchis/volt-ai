import { formatNumber } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";

interface Props {
  locale: Locale;
  /** Mean value for Monday..Sunday. */
  means: readonly number[];
  labels: readonly string[];
  scale: number;
  decimals: number;
  unit: string;
}

/** Seven bars from a zero baseline, with the value on each cap, so the weekly shape is honest. */
export function WeekdayBars({ locale, means, labels, scale, decimals, unit }: Props) {
  const max = Math.max(...means, Number.EPSILON);
  const summary = means
    .map((m, i) => `${labels[i]} ${formatNumber(m / scale, locale, decimals)}`)
    .join(", ");

  return (
    <div role="img" aria-label={`${summary} ${unit}`} className="grid grid-cols-7 items-end gap-2 pt-2">
      {means.map((mean, i) => (
        <div key={labels[i]} className="flex flex-col items-center gap-1.5">
          <span className="text-xs font-semibold tabular-nums">{formatNumber(mean / scale, locale, decimals)}</span>
          <div className="flex h-36 w-full items-end">
            <div
              className="w-full max-w-10 rounded-t-[4px] mx-auto"
              style={{ height: `${(mean / max) * 100}%`, background: "var(--c-demand)", opacity: i >= 5 ? 0.55 : 1 }}
            />
          </div>
          <span className="text-xs text-muted">{labels[i]}</span>
        </div>
      ))}
    </div>
  );
}
