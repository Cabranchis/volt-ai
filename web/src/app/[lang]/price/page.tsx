import type { Metadata } from "next";
import { HourlyChart } from "@/components/charts/HourlyChart";
import { ForecastPanel } from "@/components/pages/ForecastPanel";
import { SpikePanel } from "@/components/pages/SpikePanel";
import { DriversChart } from "@/components/ui/DriversChart";
import { Freshness } from "@/components/ui/Freshness";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { EmptyState } from "@/components/ui/States";
import { getForecast, getHourly, getSeries } from "@/lib/data";
import { formatDate } from "@/lib/format";
import { getDictionary, getLocale } from "@/lib/i18n/dictionaries";
import { lastDayOf } from "@/lib/insights";
import { spikeOutlook } from "@/lib/spikes";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.price.title, description: dict.price.description };
}

/** Latest complete day against the hourly mean of the seven days before it. */
function intradayProfiles(rows: readonly { day: string; hour: number; value: number }[]) {
  const byDay = new Map<string, (number | null)[]>();
  for (const row of rows) {
    const hours = byDay.get(row.day) ?? new Array<number | null>(24).fill(null);
    hours[row.hour - 1] = row.value;
    byDay.set(row.day, hours);
  }
  const complete = [...byDay.entries()]
    .filter(([, hours]) => hours.every((v) => v !== null))
    .sort(([a], [b]) => a.localeCompare(b));
  if (complete.length < 2) return null;
  const latest = complete[complete.length - 1] as [string, (number | null)[]];
  const previous = complete.slice(-8, -1).map(([, hours]) => hours as number[]);
  const mean = Array.from({ length: 24 }, (_, h) => previous.reduce((sum, day) => sum + (day[h] as number), 0) / previous.length);
  return { day: latest[0], latest: latest[1], previousWeek: mean };
}

export default async function PricePage() {
  const locale = await getLocale();
  const dict = await getDictionary();
  const [frame, forecast, hourly] = await Promise.all([
    getSeries(["price_mean_cop_kwh"]),
    getForecast("price_mean_cop_kwh"),
    getHourly("price_cop_kwh", 14),
  ]);

  const lastDay = lastDayOf(frame, "price_mean_cop_kwh");
  const drivers = forecast?.points[0]?.drivers ?? null;
  const intraday = intradayProfiles(hourly);
  const spikes = forecast ? spikeOutlook(forecast.points, frame.series["price_mean_cop_kwh"] ?? []) : null;

  return (
    <>
      <PageHeader
        title={dict.price.title}
        description={dict.price.description}
        meta={
          lastDay ? (
            <Freshness
              lastDay={lastDay}
              lastDayLabel={formatDate(lastDay, locale)}
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
        <ForecastPanel
          locale={locale}
          dict={dict}
          title={dict.price.chartTitle}
          tableCaption={dict.price.tableCaption}
          color="price"
          scale={1}
          decimals={0}
          unit={dict.units.copKwh}
          history={{ dates: frame.dates, values: frame.series["price_mean_cop_kwh"] ?? [] }}
          forecast={forecast}
        />

        {spikes ? <SpikePanel locale={locale} dict={dict} outlook={spikes} /> : null}

        <div className={`grid gap-6 ${drivers && drivers.length > 0 ? "lg:grid-cols-2" : ""}`}>
          {drivers && drivers.length > 0 ? (
            <Panel title={dict.price.driversTitle} note={dict.price.driversNote}>
              <DriversChart
                locale={locale}
                drivers={drivers}
                scale={1}
                decimals={0}
                unit={dict.units.copKwh}
                color="price"
                dict={dict.drivers}
              />
            </Panel>
          ) : null}
          <Panel title={dict.price.intradayTitle} note={dict.price.intradayNote}>
            {intraday ? (
              <HourlyChart
                locale={locale}
                latest={intraday.latest}
                previousWeek={intraday.previousWeek}
                latestLabel={`${dict.price.intradayLatest} (${formatDate(intraday.day, locale, "short")})`}
                weekLabel={dict.price.intradayWeek}
                hourLabel={dict.price.hour}
                unit={dict.units.copKwh}
                ariaLabel={`${dict.price.intradayTitle}. ${dict.price.intradayNote}`}
              />
            ) : (
              <EmptyState title={dict.common.noData} body={dict.common.noDataBody} />
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}
