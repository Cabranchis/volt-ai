import { Triangle } from "lucide-react";
import Link from "next/link";
import type { Anomaly } from "@/lib/data/types";
import { formatDate, formatNumber } from "@/lib/format";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";

interface Props {
  locale: Locale;
  anomalies: readonly Anomaly[];
  dict: Dictionary;
}

/** Direction is drawn as a shape (up or down triangle), never as colour alone. */
export function DirectionMark({ direction, label }: { direction: "high" | "low"; label: string }) {
  return (
    <span title={label} className="inline-flex">
      <Triangle
        role="img"
        aria-label={label}
        size={14}
        strokeWidth={2}
        className={["fill-current", direction === "low" ? "rotate-180" : ""].join(" ")}
      />
    </span>
  );
}

export function AnomalyList({ locale, anomalies, dict }: Props) {
  const targetName = (target: Anomaly["target"]) =>
    target === "demand_kwh" ? dict.kpi.demand : dict.kpi.price;

  return (
    <ol className="flex flex-col divide-y divide-line">
      {anomalies.map((a) => (
        <li key={`${a.target}-${a.day}`}>
          <Link
            href={`/${locale}/anomalies`}
            className="flex items-center justify-between gap-3 rounded py-2.5 text-sm hover:bg-surface-2"
          >
            <span className="flex items-center gap-2.5">
              <DirectionMark
                direction={a.direction}
                label={a.direction === "high" ? dict.anomalies.high : dict.anomalies.low}
              />
              <span>
                <span className="block font-medium">{formatDate(a.day, locale)}</span>
                <span className="block text-xs text-muted">{targetName(a.target)}</span>
              </span>
            </span>
            <span className="text-right tabular-nums">
              <span className="block font-semibold">{formatNumber(a.severity, locale, 1)}</span>
              <span className="block text-xs text-faint">{dict.anomalies.severity}</span>
            </span>
          </Link>
        </li>
      ))}
    </ol>
  );
}
