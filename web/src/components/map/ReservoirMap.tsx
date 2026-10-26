"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { TimeSeriesChart } from "@/components/charts/TimeSeriesChart";
import { Panel } from "@/components/ui/Panel";
import { RangeControl } from "@/components/ui/RangeControl";
import { formatDate, formatGWh, formatNumber, formatSigned } from "@/lib/format";
import { DEPARTMENTS } from "@/lib/geo/colombia";
import { reservoirLabel } from "@/lib/geo/reservoirs";
import type { RegionalData } from "@/lib/data/types";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/en";
import { fmt } from "@/lib/i18n/fmt";
import {
  bubbleRadius,
  convexHull,
  framing,
  FULL_BOX,
  isRegion,
  placeLabels,
  REGIONS,
  summarise,
  type Box,
  type MapReservoir,
  type RegionId,
} from "@/lib/regional";

type Selection = RegionId | "all";

interface Props {
  locale: Locale;
  labels: Dictionary["map"];
  day: string;
  reservoirs: readonly MapReservoir[];
  history: RegionalData["history"];
  /** The whole system, from the national series, for the view with no region chosen. */
  national: { dates: string[]; reservoirPct: (number | null)[]; inflowPct: (number | null)[] };
}

const levelColor = (level: number): string =>
  `color-mix(in oklab, var(--c-water) ${Math.round(18 + 82 * level)}%, var(--surface))`;

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** Eases the SVG view box toward its target; it jumps when the visitor prefers reduced motion. */
function useAnimatedBox(target: Box): Box {
  const [box, setBox] = useState(target);
  const current = useRef(target);
  useEffect(() => {
    // With reduced motion the first frame is already the end of the move.
    const duration = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 600;
    const from = current.current;
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const t = duration === 0 ? 1 : Math.min(1, (now - start) / duration);
      const e = 1 - Math.pow(1 - t, 3);
      const next = {
        x: lerp(from.x, target.x, e),
        y: lerp(from.y, target.y, e),
        w: lerp(from.w, target.w, e),
        h: lerp(from.h, target.h, e),
      };
      current.current = next;
      setBox(next);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target]);
  return box;
}

const lastValue = (values: readonly (number | null)[]): number | null => {
  for (let i = values.length - 1; i >= 0; i--) {
    const v = values[i];
    if (v !== null && v !== undefined) return v;
  }
  return null;
};

export function ReservoirMap({ locale, labels, day, reservoirs, history, national }: Props) {
  const [selected, setSelected] = useState<Selection>("all");
  const [hovered, setHovered] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [pixelWidth, setPixelWidth] = useState(560);

  useEffect(() => {
    const element = svgRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => entry && setPixelWidth(entry.contentRect.width || 560));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const byRegion = useMemo(() => {
    const groups = new Map<RegionId, MapReservoir[]>();
    for (const r of reservoirs) {
      if (!isRegion(r.region)) continue;
      groups.set(r.region, [...(groups.get(r.region) ?? []), r]);
    }
    return groups;
  }, [reservoirs]);

  const maxCapacity = Math.max(...reservoirs.map((r) => r.capacityKwh), 1);
  const shown = selected === "all" ? reservoirs : (byRegion.get(selected) ?? []);
  const summary = summarise(shown);
  const target = useMemo(
    () => (selected === "all" ? FULL_BOX : framing(byRegion.get(selected) ?? [], 90, 300)),
    [selected, byRegion],
  );
  const box = useAnimatedBox(target);
  const unit = box.w / pixelWidth; // map units per screen pixel, to keep bubbles and text a steady size
  const sizeScale = Math.min(1, Math.max(0.7, pixelWidth / 560));
  const radiusOf = (r: MapReservoir) => bubbleRadius(r.capacityKwh, maxCapacity) * sizeScale;

  // Names are laid out for where the view will end up, in screen pixels, so none overlap.
  const labelSpots = useMemo(() => {
    const targetUnit = target.w / pixelWidth;
    const scale = Math.min(1, Math.max(0.7, pixelWidth / 560));
    const wanted = reservoirs
      .filter((r) => r.name === hovered || (selected !== "all" && r.region === selected))
      .sort((a, b) => Number(b.name === hovered) - Number(a.name === hovered) || b.capacityKwh - a.capacityKwh);
    return placeLabels(
      reservoirs.map((r) => ({
        name: r.name,
        x: (r.x - target.x) / targetUnit,
        y: (r.y - target.y) / targetUnit,
        radius: bubbleRadius(r.capacityKwh, maxCapacity) * scale,
        width: (reservoirLabel(r.name).length + 6) * 6.4,
      })),
      15,
      4,
      wanted.map((r) => r.name),
    );
  }, [reservoirs, hovered, selected, target, pixelWidth, maxCapacity]);

  const choose = useCallback((region: string) => {
    setSelected((now) => (isRegion(region) && now !== region ? region : "all"));
  }, []);

  const regionOptions = [
    { value: "all" as const, label: labels.all },
    ...REGIONS.map((id) => ({ value: id, label: labels.regions[id] })),
  ];

  const regionHistory = selected === "all" ? null : history.regions[selected];
  const chartDates = selected === "all" ? national.dates : history.dates;
  const levelValues = (selected === "all" ? national.reservoirPct : (regionHistory?.reservoirPct ?? [])).map((v) =>
    v === null ? null : v * 100,
  );
  const inflowValues = (selected === "all" ? national.inflowPct : (regionHistory?.inflowPct ?? [])).map((v) =>
    v === null ? null : v * 100,
  );
  const inflowNow = lastValue(inflowValues);
  const title = selected === "all" ? labels.all : labels.regions[selected];

  const rows = [...shown].sort((a, b) => b.capacityKwh - a.capacityKwh);
  const mapLabel = fmt(labels.mapLabel, {
    n: reservoirs.length,
    level: summarise(reservoirs) ? `${formatNumber((summarise(reservoirs)?.level ?? 0) * 100, locale, 0)} %` : "",
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
        <Panel title={labels.panelTitle} note={fmt(labels.panelNote, { date: formatDate(day, locale) })}>
          <div className="flex flex-col gap-4">
            <RangeControl
              label={labels.regionsLabel}
              options={regionOptions}
              value={selected}
              onChange={setSelected}
              wrap
            />
            <svg
              ref={svgRef}
              viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`}
              role="group"
              aria-label={mapLabel}
              className="mx-auto block h-auto max-h-[78vh] w-full select-none"
              style={{ aspectRatio: `${FULL_BOX.w} / ${FULL_BOX.h}` }}
            >
              <g aria-hidden="true">
                {DEPARTMENTS.map((d) => (
                  <path
                    key={d.code}
                    d={d.path}
                    fill="var(--surface-2)"
                    stroke="var(--border)"
                    strokeWidth={1}
                    vectorEffect="non-scaling-stroke"
                  />
                ))}
              </g>
              <g>
                {REGIONS.map((id) => {
                  const group = byRegion.get(id);
                  if (!group) return null;
                  const active = selected === id;
                  const points = convexHull(group);
                  const first = points[0];
                  const common = {
                    fill: "var(--c-water)",
                    stroke: "var(--c-water)",
                    strokeLinejoin: "round" as const,
                    strokeLinecap: "round" as const,
                    strokeWidth: 90,
                    opacity: selected === "all" ? 0.07 : active ? 0.2 : 0.03,
                    className: "cursor-pointer transition-opacity duration-300 motion-reduce:transition-none",
                    onClick: () => choose(id),
                  };
                  return points.length >= 2 ? (
                    <polygon key={id} points={points.map((p) => `${p.x},${p.y}`).join(" ")} {...common} />
                  ) : first ? (
                    <circle key={id} cx={first.x} cy={first.y} r={45} {...common} strokeWidth={0} />
                  ) : null;
                })}
              </g>
              <g>
                {reservoirs.map((r) => {
                  const inRegion = selected === "all" || r.region === selected;
                  const radius = radiusOf(r) * unit;
                  const label = reservoirLabel(r.name);
                  const levelText = `${formatNumber(r.level * 100, locale, 0)} %`;
                  const spot = labelSpots.get(r.name);
                  return (
                    <g
                      key={r.name}
                      role="button"
                      tabIndex={0}
                      aria-label={fmt(labels.reservoirLabel, {
                        name: label,
                        level: levelText,
                        capacity: formatGWh(r.capacityKwh, locale, 0),
                      })}
                      className="cursor-pointer outline-none transition-opacity duration-300 focus-visible:[&>circle]:stroke-[var(--focus)] motion-reduce:transition-none"
                      opacity={inRegion ? 1 : 0.18}
                      onClick={() => choose(r.region)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          choose(r.region);
                        }
                      }}
                      onPointerEnter={() => setHovered(r.name)}
                      onPointerLeave={() => setHovered((now) => (now === r.name ? null : now))}
                      onFocus={() => setHovered(r.name)}
                      onBlur={() => setHovered((now) => (now === r.name ? null : now))}
                    >
                      <circle
                        cx={r.x}
                        cy={r.y}
                        r={radius}
                        fill={levelColor(r.level)}
                        stroke="var(--text-muted)"
                        strokeWidth={hovered === r.name ? 2.5 : 1.25}
                        vectorEffect="non-scaling-stroke"
                      />
                      {spot ? (
                        <text
                          x={r.x + spot.dx * unit}
                          y={r.y + spot.dy * unit}
                          textAnchor={spot.anchor}
                          dominantBaseline="central"
                          fontSize={12 * unit}
                          fill="var(--text)"
                          stroke="var(--surface)"
                          strokeWidth={4 * unit}
                          paintOrder="stroke"
                          strokeLinejoin="round"
                          pointerEvents="none"
                        >
                          {label} · {levelText}
                        </text>
                      ) : null}
                    </g>
                  );
                })}
              </g>
            </svg>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-muted">
              <div className="flex items-center gap-2">
                <span>{labels.legendTitle}</span>
                <span className="text-faint">{labels.legendLow}</span>
                <span
                  aria-hidden="true"
                  className="h-2.5 w-28 rounded-full border border-line"
                  style={{ background: `linear-gradient(to right, ${levelColor(0)}, ${levelColor(1)})` }}
                />
                <span className="text-faint">{labels.legendHigh}</span>
              </div>
              <span>{labels.sizeNote}</span>
            </div>
            <p className="max-w-[72ch] text-xs leading-relaxed text-faint">{labels.regionNote}</p>
          </div>
        </Panel>

        <Panel title={title} note={summary ? `${fmt(labels.reservoirsCount, { n: summary.count })} · ${fmt(labels.capacity, { gwh: formatGWh(summary.capacityKwh, locale, 0) })}` : undefined}>
          <div className="flex flex-col gap-5">
            <dl className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-1">
                <dt className="text-sm text-muted">{labels.level}</dt>
                <dd className="flex flex-col gap-1">
                  <span className="flex items-baseline gap-1.5">
                    <span className="text-2xl font-semibold tracking-tight">
                      {summary ? formatNumber(summary.level * 100, locale, 1) : "–"}
                    </span>
                    <span className="text-sm text-muted">%</span>
                  </span>
                  {summary?.weekChange != null ? (
                    <span className="text-xs text-muted">
                      {fmt(labels.levelDelta, { delta: formatSigned(summary.weekChange, locale) })}
                    </span>
                  ) : null}
                </dd>
              </div>
              <div className="flex flex-col gap-1">
                <dt className="text-sm text-muted">{labels.inflows}</dt>
                <dd className="flex flex-col gap-1">
                  <span className="flex items-baseline gap-1.5">
                    <span className="text-2xl font-semibold tracking-tight">
                      {inflowNow === null ? "–" : formatNumber(inflowNow, locale, 0)}
                    </span>
                    <span className="text-sm text-muted">%</span>
                  </span>
                  <span className="text-xs text-muted">{labels.inflowsNote}</span>
                </dd>
              </div>
            </dl>
            <div>
              <h3 className="font-semibold">{labels.levelChartTitle}</h3>
              <p className="mb-2 text-sm text-muted">{labels.levelChartNote}</p>
              <TimeSeriesChart
                locale={locale}
                dates={chartDates}
                series={[{ name: labels.level, values: levelValues, color: "water", kind: "area" }]}
                scale={1}
                decimals={0}
                unit="%"
                yMin={0}
                yMax={100}
                height={200}
                group="map"
                ariaLabel={`${labels.levelChartTitle}: ${title}`}
              />
            </div>
            <div>
              <h3 className="font-semibold">{labels.inflowsChartTitle}</h3>
              <p className="mb-2 text-sm text-muted">{labels.inflowsChartNote}</p>
              <TimeSeriesChart
                locale={locale}
                dates={chartDates}
                series={[{ name: labels.inflows, values: inflowValues, color: "water", kind: "line" }]}
                scale={1}
                decimals={0}
                unit="%"
                yMin={0}
                height={200}
                group="map"
                referenceLines={[{ value: 100, label: labels.meanLine }]}
                ariaLabel={`${labels.inflowsChartTitle}: ${title}`}
              />
            </div>
          </div>
        </Panel>
      </div>

      <Panel title={labels.tableTitle} note={fmt(labels.source, { date: formatDate(day, locale) })}>
        <div tabIndex={0} role="region" aria-label={labels.tableCaption} className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full border-collapse text-sm tabular-nums">
            <caption className="sr-only">{labels.tableCaption}</caption>
            <thead className="bg-surface-2 text-xs text-muted">
              <tr>
                <th scope="col" className="px-2 py-2 text-left font-medium sm:px-3">{labels.colName}</th>
                <th scope="col" className="px-2 py-2 text-left font-medium sm:px-3">{labels.colRegion}</th>
                <th scope="col" className="px-2 py-2 text-right font-medium sm:px-3">{labels.colLevel}</th>
                <th scope="col" className="px-2 py-2 text-right font-medium sm:px-3">{labels.colCapacity}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.name}
                  className="border-t border-line"
                  onPointerEnter={() => setHovered(r.name)}
                  onPointerLeave={() => setHovered((now) => (now === r.name ? null : now))}
                >
                  <th scope="row" className="px-2 py-2 text-left font-normal sm:px-3">{reservoirLabel(r.name)}</th>
                  <td className="px-2 py-2 text-left sm:px-3">{isRegion(r.region) ? labels.regions[r.region] : r.region}</td>
                  <td className="px-2 py-2 sm:px-3">
                    <span className="flex items-center justify-end gap-2">
                      <span aria-hidden="true" className="hidden h-1.5 w-20 overflow-hidden rounded-full bg-[var(--surface-2)] sm:block">
                        <span className="block h-full rounded-full" style={{ width: `${r.level * 100}%`, background: levelColor(r.level) , boxShadow: "inset 0 0 0 1px var(--text-muted)" }} />
                      </span>
                      <span className="w-12 text-right font-semibold">{formatNumber(r.level * 100, locale, 0)} %</span>
                    </span>
                  </td>
                  <td className="px-2 py-2 text-right sm:px-3">{formatGWh(r.capacityKwh, locale, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
