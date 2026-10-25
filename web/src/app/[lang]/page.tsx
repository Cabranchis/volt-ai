import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { ForecastChart } from "@/components/charts/ForecastChart";
import { AnomalyList } from "@/components/ui/AnomalyList";
import { DataTable } from "@/components/ui/DataTable";
import { Freshness } from "@/components/ui/Freshness";
import { MixBar } from "@/components/ui/MixBar";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { StatStrip, type Stat } from "@/components/ui/StatStrip";
import { EmptyState } from "@/components/ui/States";
import { getAnomalies, getBriefing, getForecast, getSeries } from "@/lib/data";
import { addDays, formatDate, formatGWh, formatNumber, formatPercent, formatSigned } from "@/lib/format";
import { getDictionary, getLocale } from "@/lib/i18n/dictionaries";
import { fmt } from "@/lib/i18n/fmt";
import {
  kpi,
  lastDayOf,
  meanOfFirst,
  MIX_SERIES_NAMES,
  mixShares,
  oniPhase,
} from "@/lib/insights";
import { buildSummary, describeForecast } from "@/lib/summary";

const SERIES = ["demand_kwh", "price_mean_cop_kwh", "reservoir_pct", "oni", ...MIX_SERIES_NAMES];
const CHART_HISTORY_DAYS = 130;

export default async function OverviewPage() {
  const locale = await getLocale();
  const dict = await getDictionary();
  const [frame, demandFc, priceFc, anomalies, briefing] = await Promise.all([
    getSeries(SERIES),
    getForecast("demand_kwh"),
    getForecast("price_mean_cop_kwh"),
    getAnomalies(5),
    getBriefing(locale),
  ]);

  const demand = kpi(frame, "demand_kwh");
  const price = kpi(frame, "price_mean_cop_kwh");
  const reservoir = kpi(frame, "reservoir_pct");
  const oni = kpi(frame, "oni", 31);
  const mixDay = lastDayOf(frame, "gen_hydro_kwh");
  const mix = mixDay ? mixShares(frame, mixDay) : null;
  const mixYearAgo = mixDay ? mixShares(frame, addDays(mixDay, -365)) : null;

  const unitText = dict.units;
  const stats: Stat[] = [];
  if (demand) {
    stats.push({
      label: dict.kpi.demand,
      value: formatGWh(demand.value, locale),
      unit: unitText.gwhDay,
      delta:
        demand.delta === null
          ? undefined
          : fmt(dict.kpi.vsWeek, { delta: formatSigned(demand.delta / 1e6, locale), unit: unitText.gwhDay }),
      deltaSign: demand.delta === null ? 0 : (Math.sign(demand.delta) as -1 | 0 | 1),
      context: fmt(dict.kpi.onDate, { date: formatDate(demand.day, locale) }),
    });
  }
  if (price) {
    stats.push({
      label: dict.kpi.price,
      value: formatNumber(price.value, locale, 0),
      unit: unitText.copKwh,
      delta:
        price.delta === null
          ? undefined
          : fmt(dict.kpi.vsWeek, { delta: formatSigned(price.delta, locale, 0), unit: unitText.copKwh }),
      deltaSign: price.delta === null ? 0 : (Math.sign(price.delta) as -1 | 0 | 1),
      context: fmt(dict.kpi.onDate, { date: formatDate(price.day, locale) }),
    });
  }
  if (reservoir) {
    stats.push({
      label: dict.kpi.reservoir,
      value: formatPercent(reservoir.value, locale).replace(" %", ""),
      unit: unitText.percent,
      delta:
        reservoir.delta === null
          ? undefined
          : fmt(dict.kpi.vsWeekPoints, { delta: formatSigned(reservoir.delta * 100, locale) }),
      deltaSign: reservoir.delta === null ? 0 : (Math.sign(reservoir.delta) as -1 | 0 | 1),
      context: fmt(dict.kpi.onDate, { date: formatDate(reservoir.day, locale) }),
    });
  }
  if (oni) {
    const phaseLabel = {
      strongNino: dict.kpi.oniStrongNino,
      nino: dict.kpi.oniNino,
      neutral: dict.kpi.oniNeutral,
      nina: dict.kpi.oniNina,
    }[oniPhase(oni.value)];
    stats.push({
      label: dict.kpi.oni,
      value: formatNumber(oni.value, locale, 2),
      unit: "",
      note: phaseLabel,
      context: fmt(dict.kpi.oniSeason, { month: formatDate(oni.day, locale, "month") }),
    });
  }

  const summaryText =
    briefing?.body ??
    buildSummary({
      locale,
      demand,
      price,
      reservoir,
      oni,
      mix,
      mixYearAgo,
      demandNextWeek: demandFc ? meanOfFirst(demandFc.points, 7) : null,
      priceNextWeek: priceFc ? meanOfFirst(priceFc.points, 7) : null,
    });
  const briefingSource = briefing?.source ?? "template";

  const tailOf = (name: string) => {
    const dates = frame.dates.slice(-CHART_HISTORY_DAYS - 3);
    const values = (frame.series[name] ?? []).slice(-CHART_HISTORY_DAYS - 3);
    return { dates, values };
  };

  const demandRows = (demandFc?.points ?? []).map((p) => ({
    date: formatDate(p.day, locale),
    p10: formatGWh(p.p10, locale),
    p50: formatGWh(p.p50, locale),
    p90: formatGWh(p.p90, locale),
  }));
  const priceRows = (priceFc?.points ?? []).map((p) => ({
    date: formatDate(p.day, locale),
    p10: formatNumber(p.p10, locale, 0),
    p50: formatNumber(p.p50, locale, 0),
    p90: formatNumber(p.p90, locale, 0),
  }));
  const tableColumns = (unit: string) => [
    { key: "date", header: dict.common.date },
    { key: "p10", header: `P10 (${unit})`, align: "right" as const },
    { key: "p50", header: `P50 (${unit})`, align: "right" as const },
    { key: "p90", header: `P90 (${unit})`, align: "right" as const },
  ];

  return (
    <>
      <PageHeader
        title={dict.overview.title}
        description={dict.overview.description}
        meta={
          demand ? (
            <Freshness
              lastDay={demand.day}
              lastDayLabel={formatDate(demand.day, locale)}
              labels={{
                dataThrough: dict.common.dataThrough,
                fresh: dict.common.freshness.fresh,
                stale: dict.common.freshness.stale,
              }}
            />
          ) : null
        }
      />

      <div className="flex flex-col gap-6">
        <Panel
          title={dict.overview.briefing}
          note={briefingSource === "gemini" ? dict.overview.briefingGemini : dict.overview.briefingTemplate}
        >
          <p className="max-w-[72ch] text-base leading-relaxed text-pretty">{summaryText}</p>
        </Panel>

        {stats.length > 0 ? <StatStrip stats={stats} /> : <EmptyState title={dict.common.noData} body={dict.common.noDataBody} />}

        <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <Panel
            title={dict.overview.demandForecast}
            note={dict.overview.demandForecastNote}
            actions={
              <Link
                href={`/${locale}/demand`}
                className="inline-flex items-center gap-1.5 text-sm font-medium text-accent-ink hover:underline"
              >
                {dict.overview.openForecast}
                <ArrowRight aria-hidden="true" size={16} strokeWidth={2} />
              </Link>
            }
          >
            {demandFc ? (
              <>
                <ForecastChart
                  locale={locale}
                  history={tailOf("demand_kwh")}
                  forecast={demandFc.points}
                  color="demand"
                  scale={1e6}
                  decimals={1}
                  unit={unitText.gwhDay}
                  labels={dict.charts}
                  ariaLabel={`${dict.overview.demandForecast}. ${describeForecast({ locale, points: demandFc.points, scale: 1e6, decimals: 1, unit: unitText.gwhDay })}`}
                  defaultRange="3m"
                  fixedRange
                  height={300}
                />
                <p className="mt-3 text-sm text-muted">
                  {describeForecast({ locale, points: demandFc.points, scale: 1e6, decimals: 1, unit: unitText.gwhDay })}
                </p>
                <DataTable
                  caption={dict.demand.tableCaption}
                  columns={tableColumns(unitText.gwhDay)}
                  rows={demandRows}
                  showLabel={dict.common.showTable}
                  hideLabel={dict.common.hideTable}
                  csv={{ href: "/api/v1/forecasts/demand?format=csv", label: dict.common.downloadCsv }}
                />
              </>
            ) : (
              <EmptyState title={dict.common.noData} body={dict.common.noDataBody} />
            )}
          </Panel>

          <Panel title={dict.overview.mixTitle} note={dict.overview.mixNote}>
            {mix ? (
              <MixBar locale={locale} shares={mix} yearAgo={mixYearAgo} labels={dict.mix} yearAgoLabel={dict.overview.mixYearAgo} />
            ) : (
              <EmptyState title={dict.common.noData} body={dict.common.noDataBody} />
            )}
          </Panel>
        </div>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <Panel
            title={dict.overview.priceForecast}
            note={dict.overview.priceForecastNote}
            actions={
              <Link
                href={`/${locale}/price`}
                className="inline-flex items-center gap-1.5 text-sm font-medium text-accent-ink hover:underline"
              >
                {dict.overview.openForecast}
                <ArrowRight aria-hidden="true" size={16} strokeWidth={2} />
              </Link>
            }
          >
            {priceFc ? (
              <>
                <ForecastChart
                  locale={locale}
                  history={tailOf("price_mean_cop_kwh")}
                  forecast={priceFc.points}
                  color="price"
                  scale={1}
                  decimals={0}
                  unit={unitText.copKwh}
                  labels={dict.charts}
                  ariaLabel={`${dict.overview.priceForecast}. ${describeForecast({ locale, points: priceFc.points, scale: 1, decimals: 0, unit: unitText.copKwh })}`}
                  defaultRange="3m"
                  fixedRange
                  height={300}
                />
                <p className="mt-3 text-sm text-muted">
                  {describeForecast({ locale, points: priceFc.points, scale: 1, decimals: 0, unit: unitText.copKwh })}
                </p>
                <DataTable
                  caption={dict.price.tableCaption}
                  columns={tableColumns(unitText.copKwh)}
                  rows={priceRows}
                  showLabel={dict.common.showTable}
                  hideLabel={dict.common.hideTable}
                  csv={{ href: "/api/v1/forecasts/price?format=csv", label: dict.common.downloadCsv }}
                />
              </>
            ) : (
              <EmptyState title={dict.common.noData} body={dict.common.noDataBody} />
            )}
          </Panel>

          <Panel
            title={dict.overview.anomaliesTitle}
            note={dict.overview.anomaliesNote}
            actions={
              <Link href={`/${locale}/anomalies`} className="text-sm font-medium text-accent-ink hover:underline">
                {dict.overview.viewAll}
              </Link>
            }
          >
            {anomalies.length > 0 ? (
              <AnomalyList locale={locale} anomalies={anomalies} dict={dict} />
            ) : (
              <EmptyState title={dict.common.noData} body={dict.common.noDataBody} />
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}
