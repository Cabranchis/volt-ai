import { SpikeChart } from "@/components/charts/SpikeChart";
import { DataTable } from "@/components/ui/DataTable";
import { Panel } from "@/components/ui/Panel";
import { formatDate, formatNumber, formatPercent } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { fmt } from "@/lib/i18n/fmt";
import { peakDay, SPIKE_LEVEL, type SpikeOutlook } from "@/lib/spikes";

interface Props {
  locale: Locale;
  dict: Dictionary;
  outlook: SpikeOutlook;
}

/** How likely each forecast day is to be expensive, read from the price forecast's own bands. */
export function SpikePanel({ locale, dict, outlook }: Props) {
  const t = dict.price.spikes;
  const level = formatNumber(SPIKE_LEVEL, locale, 0);
  const labels = {
    aboveLevel: fmt(t.aboveLevel, { level }),
    rise: t.rise,
    dayAhead: t.dayAhead,
  };
  const peakAbove = peakDay(outlook, "aboveLevel");
  const peakRise = peakDay(outlook, "rise");
  const summary = [
    fmt(t.peakLevel, {
      level,
      p: formatPercent(peakAbove.aboveLevel, locale, 0),
      date: formatDate(peakAbove.day, locale, "long"),
    }),
    fmt(t.peakRise, {
      base: formatNumber(outlook.baseline, locale, 0),
      p: formatPercent(peakRise.rise, locale, 0),
      date: formatDate(peakRise.day, locale, "long"),
    }),
  ].join(" ");

  return (
    <Panel title={t.title} note={t.note}>
      <SpikeChart locale={locale} days={outlook.days} labels={labels} ariaLabel={`${t.title}. ${summary}`} />
      <p className="mt-3 text-sm text-muted">{summary}</p>
      <p className="mt-2 text-xs text-faint">{t.caveat}</p>
      <DataTable
        caption={t.tableCaption}
        columns={[
          { key: "date", header: dict.common.date },
          { key: "level", header: fmt(t.level, { level }), align: "right" },
          { key: "rise", header: t.riseShort, align: "right" },
        ]}
        rows={outlook.days.map((d) => ({
          date: formatDate(d.day, locale, "long"),
          level: formatPercent(d.aboveLevel, locale, 0),
          rise: formatPercent(d.rise, locale, 0),
        }))}
        showLabel={dict.common.showTable}
        hideLabel={dict.common.hideTable}
      />
    </Panel>
  );
}
