import { ForecastChart } from "@/components/charts/ForecastChart";
import { DataTable } from "@/components/ui/DataTable";
import { Panel } from "@/components/ui/Panel";
import { EmptyState } from "@/components/ui/States";
import type { ForecastBundle } from "@/lib/data/types";
import { formatDate, formatNumber } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { describeForecast } from "@/lib/summary";

interface Props {
  locale: Locale;
  dict: Dictionary;
  title: string;
  note?: string;
  tableCaption: string;
  color: "demand" | "price";
  scale: number;
  decimals: number;
  unit: string;
  history: { dates: string[]; values: (number | null)[] };
  forecast: ForecastBundle | null;
  defaultRange?: "3m" | "1y" | "3y" | "all";
}

/** The chart, its one-sentence description and its data table: the unit every forecast page repeats. */
export function ForecastPanel({
  locale,
  dict,
  title,
  note,
  tableCaption,
  color,
  scale,
  decimals,
  unit,
  history,
  forecast,
  defaultRange = "1y",
}: Props) {
  if (!forecast) {
    return (
      <Panel title={title} note={note}>
        <EmptyState title={dict.common.noData} body={dict.common.noDataBody} />
      </Panel>
    );
  }

  const description = describeForecast({ locale, points: forecast.points, scale, decimals, unit });
  const rows = forecast.points.map((p) => ({
    date: formatDate(p.day, locale, "long"),
    p10: formatNumber(p.p10 / scale, locale, decimals),
    p50: formatNumber(p.p50 / scale, locale, decimals),
    p90: formatNumber(p.p90 / scale, locale, decimals),
  }));

  return (
    <Panel title={title} note={note}>
      <ForecastChart
        locale={locale}
        history={history}
        forecast={forecast.points}
        color={color}
        scale={scale}
        decimals={decimals}
        unit={unit}
        labels={dict.charts}
        ariaLabel={`${title}. ${description}`}
        defaultRange={defaultRange}
        height={380}
      />
      <p className="mt-3 text-sm text-muted">{description}</p>
      <DataTable
        caption={tableCaption}
        columns={[
          { key: "date", header: dict.common.date },
          { key: "p10", header: `P10 (${unit})`, align: "right" },
          { key: "p50", header: `P50 (${unit})`, align: "right" },
          { key: "p90", header: `P90 (${unit})`, align: "right" },
        ]}
        rows={rows}
        showLabel={dict.common.showTable}
        hideLabel={dict.common.hideTable}
      />
    </Panel>
  );
}
