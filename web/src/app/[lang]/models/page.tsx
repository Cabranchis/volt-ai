import { CircleCheck, CircleX } from "lucide-react";
import type { Metadata } from "next";
import { HorizonChart } from "@/components/charts/HorizonChart";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { EmptyState } from "@/components/ui/States";
import { getModelRun } from "@/lib/data";
import type { ForecastTarget } from "@/lib/data/types";
import { formatDate, formatNumber, formatPercent } from "@/lib/format";
import { getDictionary, getLocale } from "@/lib/i18n/dictionaries";
import { fmt } from "@/lib/i18n/fmt";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { horizonSeries, parseTargetMetrics, verdict, type TargetMetrics } from "@/lib/model-metrics";
import { REPO_URL } from "@/lib/site";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.models.title, description: dict.models.description };
}

const TARGETS: { key: ForecastTarget; color: "demand" | "price" }[] = [
  { key: "demand_kwh", color: "demand" },
  { key: "price_mean_cop_kwh", color: "price" },
];

function MetricsTable({ metrics, locale, dict }: { metrics: TargetMetrics; locale: Locale; dict: Dictionary["models"] }) {
  const rows = [
    { label: dict.rowModel, data: metrics.overall.model, strong: true },
    { label: dict.baselineNaive, data: metrics.overall.seasonal_naive, strong: false },
    { label: dict.baselineEts, data: metrics.overall.ets, strong: false },
  ];
  return (
    <div tabIndex={0} role="region" aria-label={dict.metricsTitle} className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full min-w-max border-collapse text-sm tabular-nums">
        <thead className="bg-surface-2 text-xs text-muted">
          <tr>
            <th scope="col" className="px-3 py-2 text-left font-medium">{dict.model}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{dict.mape}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{dict.mase}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{dict.coverage}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ label, data, strong }) => (
            <tr key={label} className="border-t border-line">
              <th scope="row" className={`px-3 py-2 text-left ${strong ? "font-semibold" : "font-normal"}`}>{label}</th>
              <td className="px-3 py-2 text-right">{formatNumber(data.mape, locale, 1)} %</td>
              <td className="px-3 py-2 text-right">{formatNumber(data.mase, locale, 2)}</td>
              <td className="px-3 py-2 text-right">{formatPercent(data.coverage_p10_p90, locale, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Verdicts({ metrics, locale, dict }: { metrics: TargetMetrics; locale: Locale; dict: Dictionary["models"] }) {
  const items = [
    { baseline: dict.baselineNaive, v: verdict(metrics.paired.seasonal_naive) },
    { baseline: dict.baselineEts, v: verdict(metrics.paired.ets) },
  ];
  return (
    <ul className="flex flex-col gap-2 text-sm">
      {items.map(({ baseline, v }) => (
        <li key={baseline} className="flex items-start gap-2">
          {v.beats ? (
            <CircleCheck aria-hidden="true" size={18} strokeWidth={1.75} className="mt-0.5 shrink-0 text-good" />
          ) : (
            <CircleX aria-hidden="true" size={18} strokeWidth={1.75} className="mt-0.5 shrink-0 text-serious" />
          )}
          <span>
            {fmt(v.beats ? dict.verdictBeats : dict.verdictLoses, {
              baseline,
              pct: formatNumber(v.pct, locale, 0),
              won: v.won,
              total: v.total,
            })}
          </span>
        </li>
      ))}
    </ul>
  );
}

function CoverageFigures({ metrics, locale, dict }: { metrics: TargetMetrics; locale: Locale; dict: Dictionary["models"] }) {
  const figures = [
    { label: dict.coverageRaw, value: metrics.coverage.raw },
    { label: dict.coverageCalibrated, value: metrics.coverage.calibrated },
    { label: dict.coverageTarget, value: metrics.nominal_coverage },
  ];
  return (
    <dl className="grid grid-cols-3 divide-x divide-line rounded-lg border border-line text-center">
      {figures.map(({ label, value }) => (
        <div key={label} className="flex flex-col gap-1 p-3">
          <dt className="text-xs text-muted">{label}</dt>
          <dd className="text-lg font-semibold tabular-nums">{value === null ? "–" : formatPercent(value, locale, 0)}</dd>
        </div>
      ))}
    </dl>
  );
}

export default async function ModelsPage() {
  const locale = await getLocale();
  const dict = await getDictionary();
  const run = await getModelRun();
  const m = dict.models;

  return (
    <>
      <PageHeader title={m.title} description={m.description} />
      <div className="flex flex-col gap-6">
        {run ? (
          <Panel
            title={m.lastRun}
            note={`${fmt(m.trainedOn, { start: formatDate(run.dataStart, locale), end: formatDate(run.dataEnd, locale) })} · ${fmt(m.trainedAt, { date: formatDate(run.trainedAt, locale) })}`}
          >
            <p className="max-w-[72ch] text-sm leading-relaxed text-muted">{m.metricsNote}</p>
            <p className="mt-2 max-w-[72ch] text-xs leading-relaxed text-faint">{m.metricsLegend}</p>
          </Panel>
        ) : (
          <EmptyState title={m.empty} body={dict.common.noDataBody} />
        )}

        {run
          ? TARGETS.map(({ key, color }) => {
              const metrics = parseTargetMetrics(run.metrics, key);
              const title = key === "demand_kwh" ? m.targetDemand : m.targetPrice;
              if (!metrics) {
                return (
                  <Panel key={key} title={title}>
                    <EmptyState title={m.unavailable} body={dict.common.noDataBody} />
                  </Panel>
                );
              }
              const series = horizonSeries(metrics);
              return (
                <Panel
                  key={key}
                  title={title}
                  note={fmt(m.backtestSummary, {
                    n: metrics.n_origins,
                    first: formatDate(metrics.first_origin, locale),
                    last: formatDate(metrics.last_origin, locale),
                    h: metrics.horizon,
                  })}
                >
                  <div className="flex flex-col gap-5">
                    <MetricsTable metrics={metrics} locale={locale} dict={m} />
                    <Verdicts metrics={metrics} locale={locale} dict={m} />
                    <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
                      <div>
                        <h3 className="mb-1 font-semibold">{m.horizonTitle}</h3>
                        <p className="mb-3 text-sm text-muted">{m.horizonNote}</p>
                        <HorizonChart
                          locale={locale}
                          days={series.days}
                          model={series.model}
                          seasonalNaive={series.seasonalNaive}
                          ets={series.ets}
                          labels={{ model: m.rowModel, seasonalNaive: m.baselineNaive, ets: m.baselineEts, dayAhead: m.dayAhead }}
                          color={color}
                          ariaLabel={`${m.horizonTitle}: ${title}`}
                        />
                      </div>
                      <div>
                        <h3 className="mb-1 font-semibold">{m.coverageTitle}</h3>
                        <p className="mb-3 text-sm text-muted">{m.coverageNote}</p>
                        <CoverageFigures metrics={metrics} locale={locale} dict={m} />
                      </div>
                    </div>
                  </div>
                </Panel>
              );
            })
          : null}

        <div className="grid gap-6 lg:grid-cols-2">
          <Panel title={m.methodTitle}>
            <p className="max-w-[72ch] text-sm leading-relaxed">{m.method}</p>
          </Panel>
          <Panel title={m.limitsTitle}>
            <p className="max-w-[72ch] text-sm leading-relaxed">{m.limits}</p>
            {REPO_URL ? (
              <a
                href={`${REPO_URL}/blob/main/docs/model-card.md`}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-3 inline-block text-sm font-medium text-accent-ink underline underline-offset-4"
              >
                {m.cardLink}
              </a>
            ) : null}
          </Panel>
        </div>
      </div>
    </>
  );
}
