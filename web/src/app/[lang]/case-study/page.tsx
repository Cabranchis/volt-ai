import type { Metadata } from "next";
import { CaseChart } from "@/components/charts/CaseChart";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { StatStrip, type Stat } from "@/components/ui/StatStrip";
import {
  CASE_STUDY,
  insideBand,
  lastFullMonth,
  monthProfile,
  REGIME_KEYS,
  type MonthProfile,
} from "@/lib/case-study/el-nino";
import { getSeries } from "@/lib/data";
import { formatDate, formatNumber, formatPercent } from "@/lib/format";
import { getDictionary, getLocale } from "@/lib/i18n/dictionaries";
import { fmt } from "@/lib/i18n/fmt";
import type { Locale } from "@/lib/i18n/config";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.caseStudy.title, description: dict.caseStudy.description };
}

const SERIES = [
  "price_mean_cop_kwh",
  "reservoir_pct",
  "inflows_pct",
  "gen_thermal_kwh",
  "gen_total_kwh",
  "oni",
];

const dash = "–";
const num = (v: number | null, locale: Locale, decimals = 0, suffix = "") =>
  v === null ? dash : `${formatNumber(v, locale, decimals)}${suffix}`;

export default async function CaseStudyPage() {
  const locale = await getLocale();
  const dict = await getDictionary();
  const t = dict.caseStudy;
  const frame = await getSeries(SERIES);
  const month = lastFullMonth(frame);
  const latest: MonthProfile | null = month ? monthProfile(frame, month) : null;
  const n = CASE_STUDY.regimes.all.origins;
  const won = CASE_STUDY.regimes.all.won;

  const { demand, price } = CASE_STUDY.overall;
  const stats: Stat[] = [
    {
      label: t.stats.demand,
      value: formatNumber(demand.mape, locale, 1),
      unit: "%",
      note: fmt(t.stats.versus, { ets: formatNumber(demand.etsMape, locale, 1) }),
      context: fmt(t.stats.testContext, { n: demand.origins }),
    },
    {
      label: t.stats.price,
      value: formatNumber(price.mape, locale, 1),
      unit: "%",
      note: fmt(t.stats.versus, { ets: formatNumber(price.etsMape, locale, 1) }),
      context: fmt(t.stats.testContext, { n: price.origins }),
    },
    { label: t.stats.wins, value: `${won} / ${n}`, unit: t.stats.winsUnit, context: t.stats.winsContext },
    {
      label: t.stats.band,
      value: formatNumber(price.coverage * 100, locale, 0),
      unit: "%",
      context: t.stats.bandContext,
    },
  ];

  const columns: { label: string; profile: MonthProfile | null }[] = [
    { label: t.contextLabels.oct2023, profile: CASE_STUDY.months["2023-10"] ?? null },
    { label: t.contextLabels.dec2023, profile: CASE_STUDY.months["2023-12"] ?? null },
    {
      label: month ? `${t.contextLabels.latest} (${formatDate(`${month}-01`, locale, "month")})` : t.contextLabels.latest,
      profile: latest,
    },
  ];
  const contextRows: { label: string; value: (p: MonthProfile) => string }[] = [
    { label: t.contextRows.price, value: (p) => num(p.price, locale) },
    { label: t.contextRows.reservoir, value: (p) => num(p.reservoirMin, locale, 0, " %") },
    { label: t.contextRows.inflows, value: (p) => num(p.inflows, locale, 0, " %") },
    { label: t.contextRows.thermal, value: (p) => num(p.thermal, locale, 0, " %") },
    { label: t.contextRows.oni, value: (p) => num(p.oni, locale, 1) },
  ];
  const head = "px-2 py-2 text-right font-medium sm:px-3";

  return (
    <>
      <PageHeader title={t.title} description={t.description} />
      <div className="flex flex-col gap-6">
        <StatStrip stats={stats} />

        <Panel title={t.regimesTitle} note={t.regimesNote}>
          <div tabIndex={0} role="region" aria-label={t.regimesTitle} className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full border-collapse text-sm tabular-nums">
              <thead className="bg-surface-2 text-xs text-muted">
                <tr>
                  <th scope="col" className="px-2 py-2 text-left font-medium sm:px-3">{t.columns.period}</th>
                  <th scope="col" className={head}>{t.columns.origins}</th>
                  <th scope="col" className={head}>{t.columns.model}</th>
                  <th scope="col" className={head}>{t.columns.ets}</th>
                  <th scope="col" className={head}>{t.columns.naive}</th>
                  <th scope="col" className={head}>{t.columns.coverage}</th>
                </tr>
              </thead>
              <tbody>
                {REGIME_KEYS.map((key) => {
                  const r = CASE_STUDY.regimes[key];
                  return (
                    <tr key={key} className="border-t border-line">
                      <th scope="row" className={`min-w-44 px-2 py-2 text-left sm:px-3 ${key === "all" ? "font-semibold" : "font-normal"}`}>
                        {fmt(t.regimes[key], { n })}
                      </th>
                      <td className="px-2 py-2 text-right sm:px-3">{r.origins}</td>
                      <td className="px-2 py-2 text-right font-semibold sm:px-3">{formatNumber(r.model, locale, 2)}</td>
                      <td className="px-2 py-2 text-right sm:px-3">{formatNumber(r.ets, locale, 2)}</td>
                      <td className="px-2 py-2 text-right sm:px-3">{formatNumber(r.naive, locale, 2)}</td>
                      <td className="px-2 py-2 text-right sm:px-3">{formatPercent(r.coverage, locale, 0)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-4 max-w-[72ch] text-sm leading-relaxed text-muted">{t.regimesReading}</p>
        </Panel>

        <Panel title={t.contextTitle} note={t.contextNote}>
          <div tabIndex={0} role="region" aria-label={t.contextTitle} className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full border-collapse text-sm tabular-nums">
              <thead className="bg-surface-2 text-xs text-muted">
                <tr>
                  <th scope="col" className="px-2 py-2 text-left font-medium sm:px-3">
                    <span className="sr-only">{t.contextTitle}</span>
                  </th>
                  {columns.map((c) => (
                    <th key={c.label} scope="col" className={head}>
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {contextRows.map((row) => (
                  <tr key={row.label} className="border-t border-line">
                    <th scope="row" className="min-w-44 px-2 py-2 text-left font-normal sm:px-3">
                      {row.label}
                    </th>
                    {columns.map((c) => (
                      <td key={c.label} className="px-2 py-2 text-right sm:px-3">
                        {c.profile ? row.value(c.profile) : dash}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-4 max-w-[72ch] text-sm leading-relaxed text-muted">{t.contextReading}</p>
        </Panel>

        <section aria-labelledby="cases-title" className="flex flex-col gap-4">
          <div>
            <h2 id="cases-title" className="text-lg font-semibold tracking-tight">
              {t.casesTitle}
            </h2>
            <p className="mt-0.5 max-w-[72ch] text-sm text-muted">{fmt(t.casesNote, { won, n })}</p>
          </div>
          {CASE_STUDY.cases.map((point) => {
            const text = t.cases.find((c) => c.origin === point.origin);
            if (!text) return null;
            const band = insideBand(point);
            return (
              <Panel key={point.origin} title={text.title} note={formatDate(point.origin, locale, "long")} as="h3">
                <CaseChart locale={locale} point={point} labels={t.chart} ariaLabel={`${text.title}. ${text.reading}`} />
                <p className="mt-4 max-w-[72ch] text-sm leading-relaxed">{text.reading}</p>
                <p className="mt-2 text-xs text-muted tabular-nums">
                  {fmt(t.scoreLine, {
                    mapeModel: formatNumber(point.scores.mapeModel, locale, 0),
                    mapeEts: formatNumber(point.scores.mapeEts, locale, 0),
                    inside: band.inside,
                    total: band.total,
                  })}
                </p>
              </Panel>
            );
          })}
        </section>

        <Panel title={t.limitsTitle}>
          <ul className="flex max-w-[72ch] list-disc flex-col gap-2 pl-5 text-sm leading-relaxed">
            {t.limits.map((item) => (
              <li key={item}>{fmt(item, { n, won })}</li>
            ))}
          </ul>
          <p className="mt-4 text-xs text-muted">{fmt(t.method, { runId: CASE_STUDY.runId })}</p>
        </Panel>
      </div>
    </>
  );
}
