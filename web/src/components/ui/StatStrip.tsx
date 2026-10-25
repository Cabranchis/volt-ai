import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

export interface Stat {
  label: string;
  /** Pre-formatted value, e.g. "248.5". */
  value: string;
  unit: string;
  /** Pre-formatted delta text, e.g. "+3.2 GWh/day vs 7 days earlier". */
  delta?: string;
  deltaSign?: -1 | 0 | 1;
  /** Plain remark without a direction arrow, e.g. the El Niño phase. */
  note?: string;
  /** Short context line, e.g. the date the value belongs to. */
  context: string;
}

/**
 * The headline figures as one ruled strip. Each figure keeps its own date, because XM settles
 * demand, price and hydrology on different days.
 */
export function StatStrip({ stats }: { stats: readonly Stat[] }) {
  return (
    <dl className="grid grid-cols-1 divide-y divide-line glass-strong glow rounded-panel sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-4 lg:divide-x">
      {stats.map((stat, index) => (
        <div
          key={stat.label}
          className={[
            "flex flex-col gap-1.5 p-5",
            index >= 2 ? "sm:border-t sm:border-line lg:border-t-0" : "",
            index % 2 === 1 ? "sm:border-l sm:border-line lg:border-l-0" : "",
          ].join(" ")}
        >
          <dt className="text-sm text-muted">{stat.label}</dt>
          <dd className="flex flex-col gap-1.5">
            <span className="flex items-baseline gap-1.5">
              <span className="text-2xl font-semibold tracking-tight">{stat.value}</span>
              <span className="text-sm text-muted">{stat.unit}</span>
            </span>
            {stat.delta ? (
              <span className="flex items-center gap-1 text-xs text-muted">
                {stat.deltaSign === 1 ? (
                  <ArrowUpRight aria-hidden="true" size={14} strokeWidth={2} />
                ) : stat.deltaSign === -1 ? (
                  <ArrowDownRight aria-hidden="true" size={14} strokeWidth={2} />
                ) : (
                  <Minus aria-hidden="true" size={14} strokeWidth={2} />
                )}
                {stat.delta}
              </span>
            ) : null}
            {stat.note ? <span className="text-xs text-muted">{stat.note}</span> : null}
            <span className="text-xs text-faint">{stat.context}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}
