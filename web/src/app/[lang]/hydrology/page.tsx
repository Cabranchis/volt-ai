import type { Metadata } from "next";
import { HydrologyExplorer } from "@/components/charts/HydrologyExplorer";
import { MixAreaChart } from "@/components/charts/MixAreaChart";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { EmptyState } from "@/components/ui/States";
import { getSeries } from "@/lib/data";
import { getDictionary, getLocale } from "@/lib/i18n/dictionaries";
import { MIX_SERIES_NAMES, monthlyMix } from "@/lib/insights";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.hydrology.title, description: dict.hydrology.description };
}

const SERIES = [
  "reservoir_pct",
  "inflows_kwh",
  "inflows_hist_mean_kwh",
  "oni",
  "price_mean_cop_kwh",
  ...MIX_SERIES_NAMES,
];

export default async function HydrologyPage() {
  const locale = await getLocale();
  const dict = await getDictionary();
  const frame = await getSeries(SERIES);
  const column = (name: string) => frame.series[name] ?? [];
  const mix = monthlyMix(frame);

  return (
    <>
      <PageHeader title={dict.hydrology.title} description={dict.hydrology.description} />
      <div className="flex flex-col gap-6">
        <p className="max-w-[72ch] text-sm leading-relaxed text-muted">{dict.hydrology.reading}</p>

        <HydrologyExplorer
          locale={locale}
          dates={frame.dates}
          reservoirPct={column("reservoir_pct")}
          inflowsKwh={column("inflows_kwh")}
          inflowsHistMeanKwh={column("inflows_hist_mean_kwh")}
          oni={column("oni")}
          priceMean={column("price_mean_cop_kwh")}
          dict={dict}
        />

        <Panel title={dict.hydrology.mixTitle} note={dict.hydrology.mixNote}>
          {mix.months.length > 0 ? (
            <MixAreaChart
              locale={locale}
              months={mix.months}
              shares={mix.shares}
              labels={dict.mix}
              ariaLabel={`${dict.hydrology.mixTitle}. ${dict.hydrology.mixNote}`}
            />
          ) : (
            <EmptyState title={dict.common.noData} body={dict.common.noDataBody} />
          )}
        </Panel>
      </div>
    </>
  );
}
