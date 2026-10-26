import { Panel } from "@/components/ui/Panel";
import { formatDate, formatNumber, formatPercent } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { fmt } from "@/lib/i18n/fmt";
import type { TrackRecord } from "@/lib/track-record";

interface Props {
  locale: Locale;
  dict: Dictionary["models"];
  entries: { key: "demand" | "price"; title: string; record: TrackRecord }[];
}

/** Forecasts as issued against what happened, so the accuracy claim can be checked day by day. */
export function TrackRecordPanel({ locale, dict, entries }: Props) {
  const t = dict.live;
  const anyScored = entries.some((e) => e.record.scored > 0);
  return (
    <Panel title={t.title} note={t.note}>
      {anyScored ? (
        <div className="flex flex-col gap-6">
          {entries.map(({ key, title, record }) =>
            record.scored === 0 ? null : (
              <section key={key} className="flex flex-col gap-3">
                <h3 className="font-semibold">{title}</h3>
                <p className="max-w-[72ch] text-sm text-muted">
                  {fmt(t.summary, {
                    n: record.scored,
                    first: formatDate(record.firstDay ?? "", locale),
                    last: formatDate(record.lastDay ?? "", locale),
                    pending: record.pending,
                  })}
                  {record.winShare !== null ? ` ${fmt(t.win, { p: formatPercent(record.winShare, locale, 0) })}` : ""}
                </p>
                <div tabIndex={0} role="region" aria-label={`${title}. ${t.tableCaption}`} className="overflow-x-auto rounded-lg border border-line">
                  <table className="w-full border-collapse text-sm tabular-nums">
                    <caption className="sr-only">{`${title}. ${t.tableCaption}`}</caption>
                    <thead className="bg-surface-2 text-xs text-muted">
                      <tr>
                        <th scope="col" className="px-2 py-2 text-left font-medium sm:px-3">{t.horizon}</th>
                        <th scope="col" className="px-2 py-2 text-right font-medium sm:px-3">{t.count}</th>
                        <th scope="col" className="px-2 py-2 text-right font-medium sm:px-3">{t.errModel}</th>
                        <th scope="col" className="px-2 py-2 text-right font-medium sm:px-3">{t.errNaive}</th>
                        <th scope="col" className="px-2 py-2 text-right font-medium sm:px-3">{t.coverage}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {record.buckets.map((b) => (
                        <tr key={b.from} className="border-t border-line">
                          <th scope="row" className="px-2 py-2 text-left font-normal sm:px-3">
                            {fmt(t.days, { from: b.from, to: b.to })}
                          </th>
                          <td className="px-2 py-2 text-right sm:px-3">{b.n}</td>
                          <td className="px-2 py-2 text-right font-semibold sm:px-3">{formatNumber(b.mape, locale, 1)} %</td>
                          <td className="px-2 py-2 text-right sm:px-3">
                            {b.naiveMape === null ? "–" : `${formatNumber(b.naiveMape, locale, 1)} %`}
                          </td>
                          <td className="px-2 py-2 text-right sm:px-3">{formatPercent(b.coverage, locale, 0)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="text-xs text-faint">{key === "demand" ? t.naiveDemand : t.naivePrice}</p>
              </section>
            ),
          )}
          <p className="max-w-[72ch] text-xs leading-relaxed text-faint">{t.few}</p>
        </div>
      ) : (
        <p className="max-w-[72ch] text-sm leading-relaxed text-muted">{t.empty}</p>
      )}
    </Panel>
  );
}
