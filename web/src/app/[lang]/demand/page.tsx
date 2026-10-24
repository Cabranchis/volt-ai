import type { Metadata } from "next";
import { ForecastPanel } from "@/components/pages/ForecastPanel";
import { DriversChart } from "@/components/ui/DriversChart";
import { Freshness } from "@/components/ui/Freshness";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { WeekdayBars } from "@/components/ui/WeekdayBars";
import { getForecast, getSeries } from "@/lib/data";
import { formatDate } from "@/lib/format";
import { getDictionary, getLocale } from "@/lib/i18n/dictionaries";
import { lastDayOf, weekdayProfile } from "@/lib/insights";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.demand.title, description: dict.demand.description };
}

export default async function DemandPage() {
  const locale = await getLocale();
  const dict = await getDictionary();
  const [frame, forecast] = await Promise.all([getSeries(["demand_kwh"]), getForecast("demand_kwh")]);

  const lastDay = lastDayOf(frame, "demand_kwh");
  const profile = weekdayProfile(frame, "demand_kwh", 365);
  const drivers = forecast?.points[0]?.drivers ?? null;

  return (
    <>
      <PageHeader
        title={dict.demand.title}
        description={dict.demand.description}
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
          title={dict.demand.chartTitle}
          tableCaption={dict.demand.tableCaption}
          color="demand"
          scale={1e6}
          decimals={1}
          unit={dict.units.gwhDay}
          history={{ dates: frame.dates, values: frame.series["demand_kwh"] ?? [] }}
          forecast={forecast}
        />

        <div className={`grid gap-6 ${drivers && drivers.length > 0 ? "lg:grid-cols-2" : ""}`}>
          {drivers && drivers.length > 0 ? (
            <Panel title={dict.demand.driversTitle} note={dict.demand.driversNote}>
              <DriversChart
                locale={locale}
                drivers={drivers}
                scale={1e6}
                decimals={1}
                unit={dict.units.gwhDay}
                color="demand"
                dict={dict.drivers}
              />
            </Panel>
          ) : null}
          <Panel title={dict.demand.profileTitle} note={dict.demand.profileNote}>
            <WeekdayBars
              locale={locale}
              means={profile.map((p) => p.mean)}
              labels={dict.demand.weekdays.split(",")}
              scale={1e6}
              decimals={0}
              unit={dict.units.gwhDay}
            />
          </Panel>
        </div>
      </div>
    </>
  );
}
