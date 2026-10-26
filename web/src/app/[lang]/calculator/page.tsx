import type { Metadata } from "next";
import { CostCalculator } from "@/components/pages/CostCalculator";
import { Freshness } from "@/components/ui/Freshness";
import { PageHeader } from "@/components/ui/PageHeader";
import { getForecast, getSeries } from "@/lib/data";
import { formatDate } from "@/lib/format";
import { getDictionary, getLocale } from "@/lib/i18n/dictionaries";
import { lastDayOf } from "@/lib/insights";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.calculator.title, description: dict.calculator.description };
}

export default async function CalculatorPage() {
  const locale = await getLocale();
  const dict = await getDictionary();
  const [frame, forecast] = await Promise.all([getSeries(["price_mean_cop_kwh"]), getForecast("price_mean_cop_kwh")]);
  const lastDay = lastDayOf(frame, "price_mean_cop_kwh");

  return (
    <>
      <PageHeader
        title={dict.calculator.title}
        description={dict.calculator.description}
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
      <CostCalculator locale={locale} dict={dict} points={forecast?.points ?? []} />
    </>
  );
}
