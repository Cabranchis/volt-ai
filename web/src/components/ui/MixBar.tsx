import { formatPercent } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { fmt } from "@/lib/i18n/fmt";
import { MIX_ORDER, type MixKey, type MixShares } from "@/lib/insights";

const COLOR: Record<MixKey, string> = {
  thermal: "var(--c-thermal)",
  hydro: "var(--c-water)",
  wind: "var(--c-wind)",
  solar: "var(--c-solar)",
  cogen: "var(--c-cogen)",
  other: "var(--c-other)",
};

interface Props {
  locale: Locale;
  shares: MixShares;
  yearAgo: MixShares | null;
  labels: Dictionary["mix"];
  yearAgoLabel: string;
}

/**
 * One composition bar plus a list with the exact shares. A single bar reads faster than a donut,
 * and the list carries the values, so colour never has to do the work alone.
 */
export function MixBar({ locale, shares, yearAgo, labels, yearAgoLabel }: Props) {
  const summary = MIX_ORDER.map((k) => `${labels[k]} ${formatPercent(shares[k], locale, 0)}`).join(", ");

  return (
    <div className="flex flex-col gap-4">
      <div role="img" aria-label={summary} className="flex h-4 w-full gap-0.5 overflow-hidden rounded-md">
        {MIX_ORDER.filter((k) => shares[k] > 0.0005).map((k) => (
          <span key={k} style={{ width: `${shares[k] * 100}%`, background: COLOR[k] }} />
        ))}
      </div>
      <ul className="flex flex-col divide-y divide-line text-sm">
        {[...MIX_ORDER]
          .sort((a, b) => shares[b] - shares[a])
          .map((k) => (
            <li key={k} className="flex items-center justify-between gap-3 py-2">
              <span className="flex items-center gap-2">
                <span aria-hidden="true" className="size-3 rounded-[3px]" style={{ background: COLOR[k] }} />
                {labels[k]}
              </span>
              <span className="flex items-baseline gap-3 tabular-nums">
                {yearAgo ? (
                  <span className="text-xs text-faint">
                    {fmt(yearAgoLabel, { share: formatPercent(yearAgo[k], locale, 0) })}
                  </span>
                ) : null}
                <span className="w-12 text-right font-semibold">{formatPercent(shares[k], locale, 1)}</span>
              </span>
            </li>
          ))}
      </ul>
    </div>
  );
}
