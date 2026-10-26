import type { Metadata } from "next";
import { ReservoirMap } from "@/components/map/ReservoirMap";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/States";
import { getRegional, getSeries } from "@/lib/data";
import { getDictionary, getLocale } from "@/lib/i18n/dictionaries";
import { placeReservoirs } from "@/lib/regional";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.map.title, description: dict.map.description };
}

export default async function MapPage() {
  const locale = await getLocale();
  const dict = await getDictionary();
  const regional = await getRegional();
  const reservoirs = regional ? placeReservoirs(regional) : [];

  return (
    <>
      <PageHeader title={dict.map.title} description={dict.map.description} />
      {regional && reservoirs.length > 0 ? (
        <ReservoirMap
          locale={locale}
          labels={dict.map}
          day={regional.day}
          reservoirs={reservoirs}
          history={regional.history}
          national={await nationalHistory(regional.history.dates)}
        />
      ) : (
        <EmptyState title={dict.map.empty} body={dict.map.emptyBody} />
      )}
    </>
  );
}

/** The whole system on the same dates as the regional history, from the national series. */
async function nationalHistory(dates: string[]) {
  const first = dates[0];
  const frame = await getSeries(["reservoir_pct", "inflows_pct"], first);
  return {
    dates: frame.dates,
    reservoirPct: frame.series["reservoir_pct"] ?? [],
    inflowPct: frame.series["inflows_pct"] ?? [],
  };
}
