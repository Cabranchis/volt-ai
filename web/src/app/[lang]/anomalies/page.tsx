import type { Metadata } from "next";
import { AnomaliesExplorer } from "@/components/charts/AnomaliesExplorer";
import { PageHeader } from "@/components/ui/PageHeader";
import { getAnomalies, getSeries } from "@/lib/data";
import { getDictionary, getLocale } from "@/lib/i18n/dictionaries";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.anomalies.title, description: dict.anomalies.description };
}

export default async function AnomaliesPage() {
  const locale = await getLocale();
  const dict = await getDictionary();
  const [frame, anomalies] = await Promise.all([
    getSeries(["demand_kwh", "price_mean_cop_kwh"]),
    getAnomalies(300),
  ]);

  return (
    <>
      <PageHeader title={dict.anomalies.title} description={dict.anomalies.description} />
      <AnomaliesExplorer
        locale={locale}
        dict={dict}
        dates={frame.dates}
        values={{
          demand_kwh: frame.series["demand_kwh"] ?? [],
          price_mean_cop_kwh: frame.series["price_mean_cop_kwh"] ?? [],
        }}
        anomalies={anomalies}
      />
    </>
  );
}
