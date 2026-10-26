import { CloudRain, FileText, Gauge, Mail, ShieldCheck, Zap } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { EmptyState } from "@/components/ui/States";
import { getModelRun } from "@/lib/data";
import { formatNumber } from "@/lib/format";
import { getDictionary, getLocale } from "@/lib/i18n/dictionaries";
import { fmt } from "@/lib/i18n/fmt";
import type { Locale } from "@/lib/i18n/config";
import { bucketErrors, parseTargetMetrics } from "@/lib/model-metrics";
import { CONTACT_EMAIL, hrefFor } from "@/lib/site";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.business.title, description: dict.business.description };
}

const SAMPLE_REPORT = "/informe-ejemplo-volt-ai.pdf";

interface ErrorRow {
  label: string;
  model: number;
  naive: number;
  ets: number;
}

export default async function BusinessPage() {
  const locale: Locale = await getLocale();
  const dict = await getDictionary();
  const b = dict.business;
  const run = await getModelRun();

  const demand = run ? parseTargetMetrics(run.metrics, "demand_kwh") : null;
  const price = run ? parseTargetMetrics(run.metrics, "price_mean_cop_kwh") : null;
  const rows: ErrorRow[] = [];
  if (demand) {
    const o = demand.overall;
    rows.push({ label: b.demandRow, model: o.model.mape, naive: o.seasonal_naive.mape, ets: o.ets.mape });
  }
  if (price) {
    for (const bucket of bucketErrors(price)) {
      rows.push({
        label: fmt(b.priceRow, { range: bucket.label.replace("-", "–") }),
        model: bucket.model,
        naive: bucket.seasonalNaive,
        ets: bucket.ets,
      });
    }
  }
  const origins = Math.min(demand?.n_origins ?? Infinity, price?.n_origins ?? Infinity);
  const hasPriceRows = rows.length > (demand ? 1 : 0);

  const heroDemand = demand?.overall.model.mape;
  const heroPrice = price ? bucketErrors(price)[0]?.model : undefined;
  const hero = [
    heroDemand !== undefined ? { label: b.heroDemand, value: `${formatNumber(heroDemand, locale, 1)} %` } : null,
    heroPrice !== undefined ? { label: b.heroPrice, value: `${formatNumber(heroPrice, locale, 1)} %` } : null,
    Number.isFinite(origins) ? { label: b.heroTests, value: String(origins) } : null,
  ].filter((item): item is { label: string; value: string } => item !== null);

  const gets = [
    { Icon: Zap, ...b.get[0] },
    { Icon: Gauge, ...b.get[1] },
    { Icon: CloudRain, ...b.get[2] },
    { Icon: ShieldCheck, ...b.get[3] },
  ];

  return (
    <>
      <PageHeader title={b.title} description={b.description} />
      <div className="flex flex-col gap-6">
        {hero.length > 0 ? (
          <section aria-label={b.numbersTitle} className="glass-strong glow rounded-panel p-5 sm:p-6">
            <dl className="grid gap-5 sm:grid-cols-3">
              {hero.map((item) => (
                <div key={item.label} className="flex flex-col gap-1">
                  <dd className="order-1 text-3xl font-semibold tracking-tight text-accent-ink tabular-nums">{item.value}</dd>
                  <dt className="order-2 text-sm text-muted">{item.label}</dt>
                </div>
              ))}
            </dl>
            <p className="mt-3 text-xs text-faint">{b.heroNote}</p>
            <div className="mt-4 flex flex-wrap gap-3">
              <a
                href={`mailto:${CONTACT_EMAIL}`}
                className="btn-primary inline-flex min-h-11 items-center gap-2 rounded-lg px-4 text-sm font-medium"
              >
                <Mail aria-hidden="true" size={16} strokeWidth={1.75} />
                {b.contactCta}
              </a>
              <a
                href={SAMPLE_REPORT}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-glass inline-flex min-h-11 items-center gap-2 rounded-lg px-4 text-sm font-medium"
              >
                <FileText aria-hidden="true" size={16} strokeWidth={1.75} />
                {b.reportCta}
              </a>
            </div>
          </section>
        ) : null}

        <Panel title={b.forWhoTitle}>
          <ul className="flex list-disc flex-col gap-2 pl-5 text-sm leading-relaxed marker:text-faint">
            {b.forWho.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Panel>

        <Panel title={b.getTitle}>
          <ul className="grid gap-5 sm:grid-cols-2">
            {gets.map(({ Icon, title, body }) => (
              <li key={title} className="flex flex-col gap-1.5">
                <h3 className="flex items-center gap-2 font-semibold">
                  <Icon aria-hidden="true" size={18} strokeWidth={1.75} className="shrink-0 text-accent-ink" />
                  {title}
                </h3>
                <p className="text-sm leading-relaxed text-muted">{body}</p>
              </li>
            ))}
          </ul>
        </Panel>

        {rows.length === 0 ? (
          <Panel title={b.numbersTitle}>
            <EmptyState title={dict.models.unavailable} body={dict.common.noDataBody} />
          </Panel>
        ) : (
          <Panel
            title={b.numbersTitle}
            note={fmt(b.numbersNote, { n: Number.isFinite(origins) ? origins : "" })}
          >
            <div
              tabIndex={0}
              role="region"
              aria-label={b.numbersTitle}
              className="overflow-x-auto rounded-lg border border-line"
            >
              <table className="w-full border-collapse text-sm tabular-nums">
                <thead className="bg-surface-2 text-xs text-muted">
                  <tr>
                    <th scope="col" className="px-2 py-2 text-left font-medium sm:w-2/5 sm:px-3">{b.horizon}</th>
                    <th scope="col" className="px-2 py-2 text-right font-medium sm:px-3">{dict.models.rowModel}</th>
                    <th scope="col" className="px-2 py-2 text-right font-medium sm:px-3">{dict.models.baselineNaive}</th>
                    <th scope="col" className="px-2 py-2 text-right font-medium sm:px-3">{dict.models.baselineEts}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.label} className="border-t border-line">
                      <th scope="row" className="px-2 py-2 text-left font-normal sm:px-3">{row.label}</th>
                      <td className="whitespace-nowrap px-2 py-2 text-right font-semibold sm:px-3">{formatNumber(row.model, locale, 1)} %</td>
                      <td className="whitespace-nowrap px-2 py-2 text-right sm:px-3">{formatNumber(row.naive, locale, 1)} %</td>
                      <td className="whitespace-nowrap px-2 py-2 text-right sm:px-3">{formatNumber(row.ets, locale, 1)} %</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {hasPriceRows ? (
              <p className="mt-3 max-w-[72ch] text-xs leading-relaxed text-muted">{b.numbersFoot}</p>
            ) : null}
          </Panel>
        )}

        <div className="grid items-start gap-6 lg:grid-cols-2">
          <Panel title={b.trackTitle}>
            <p className="text-sm leading-relaxed text-muted">{b.trackBody}</p>
            <Link
              href={hrefFor(locale, "/models")}
              className="mt-3 inline-block text-sm font-medium text-accent-ink underline underline-offset-4"
            >
              {b.trackCta}
            </Link>
          </Panel>
          <Panel title={b.limitsTitle}>
            <ul className="flex list-disc flex-col gap-2 pl-5 text-sm leading-relaxed marker:text-faint">
              {b.limits.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </Panel>
        </div>

        <Panel title={b.reportTitle}>
          <p className="max-w-[72ch] text-sm leading-relaxed text-muted">{b.reportBody}</p>
          <a
            href={SAMPLE_REPORT}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-glass mt-3 inline-flex min-h-11 items-center gap-2 rounded-lg px-4 text-sm font-medium"
          >
            <FileText aria-hidden="true" size={16} strokeWidth={1.75} />
            {b.reportCta}
          </a>
        </Panel>

        <Panel title={b.contactTitle}>
          <p className="max-w-[72ch] text-sm leading-relaxed text-muted">{b.contactBody}</p>
          <a
            href={`mailto:${CONTACT_EMAIL}`}
            className="btn-primary mt-3 inline-flex min-h-11 items-center gap-2 rounded-lg px-4 text-sm font-medium"
          >
            <Mail aria-hidden="true" size={16} strokeWidth={1.75} />
            {b.contactCta}
          </a>
          <p className="mt-3 text-xs text-faint">
            {CONTACT_EMAIL} · {b.contactNote}
          </p>
        </Panel>
      </div>
    </>
  );
}
