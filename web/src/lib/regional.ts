import type { RegionalData } from "./data/types";
import { MAP_SIZE, PROJECTION } from "./geo/colombia";
import { RESERVOIR_SITES } from "./geo/reservoirs";

/** XM's hydrological regions, in the order the page lists them (north to south, roughly). */
export const REGIONS = ["CARIBE", "ANTIOQUIA", "CALDAS", "CENTRO", "ORIENTE", "VALLE"] as const;
export type RegionId = (typeof REGIONS)[number];

export const isRegion = (value: string): value is RegionId => (REGIONS as readonly string[]).includes(value);

export interface Point {
  x: number;
  y: number;
}

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export const FULL_BOX: Box = { x: 0, y: 0, w: MAP_SIZE.width, h: MAP_SIZE.height };

/** Equirectangular projection shared with tools/build_colombia_map.py. */
export function projectPoint(lat: number, lon: number): Point {
  return { x: (lon - PROJECTION.lon0) * PROJECTION.kx, y: (PROJECTION.lat0 - lat) * PROJECTION.scale };
}

export interface MapReservoir {
  name: string;
  region: string;
  volumeKwh: number;
  capacityKwh: number;
  weekAgoKwh: number | null;
  /** Fraction of the usable capacity that is full, 0 to 1. */
  level: number;
  x: number;
  y: number;
}

/** Reservoirs that XM reports and that have a place on the map. */
export function placeReservoirs(data: RegionalData): MapReservoir[] {
  return data.reservoirs.flatMap((r) => {
    const site = RESERVOIR_SITES[r.name];
    if (!site || r.capacityKwh <= 0) return [];
    const { x, y } = projectPoint(site.lat, site.lon);
    return [{ ...r, level: Math.min(1, Math.max(0, r.volumeKwh / r.capacityKwh)), x, y }];
  });
}

export interface LevelSummary {
  count: number;
  volumeKwh: number;
  capacityKwh: number;
  level: number;
  /** Change in percentage points over the last 7 days, when every reservoir has the older value. */
  weekChange: number | null;
}

export function summarise(reservoirs: readonly MapReservoir[]): LevelSummary | null {
  if (reservoirs.length === 0) return null;
  const volumeKwh = reservoirs.reduce((s, r) => s + r.volumeKwh, 0);
  const capacityKwh = reservoirs.reduce((s, r) => s + r.capacityKwh, 0);
  const complete = reservoirs.every((r) => r.weekAgoKwh !== null);
  const before = complete ? reservoirs.reduce((s, r) => s + (r.weekAgoKwh as number), 0) / capacityKwh : null;
  const level = volumeKwh / capacityKwh;
  return {
    count: reservoirs.length,
    volumeKwh,
    capacityKwh,
    level,
    weekChange: before === null ? null : (level - before) * 100,
  };
}

/** Convex hull (Andrew's monotone chain), counter-clockwise on screen coordinates. */
export function convexHull(points: readonly Point[]): Point[] {
  const sorted = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
  if (sorted.length < 3) return sorted;
  const cross = (o: Point, a: Point, b: Point) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const build = (input: readonly Point[]) => {
    const hull: Point[] = [];
    for (const p of input) {
      while (hull.length >= 2 && cross(hull[hull.length - 2] as Point, hull[hull.length - 1] as Point, p) <= 0) hull.pop();
      hull.push(p);
    }
    hull.pop();
    return hull;
  };
  return [...build(sorted), ...build([...sorted].reverse())];
}

/** The box that holds the points with room around them, never smaller than `min` and in the page's aspect. */
export function framing(points: readonly Point[], pad: number, min: number): Box {
  if (points.length === 0) return FULL_BOX;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const x0 = Math.min(...xs) - pad;
  const x1 = Math.max(...xs) + pad;
  const y0 = Math.min(...ys) - pad;
  const y1 = Math.max(...ys) + pad;
  const aspect = FULL_BOX.w / FULL_BOX.h;
  let w = Math.max(x1 - x0, min);
  let h = Math.max(y1 - y0, min);
  if (w / h > aspect) h = w / aspect;
  else w = h * aspect;
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  const x = Math.min(Math.max(cx - w / 2, FULL_BOX.x), Math.max(FULL_BOX.w - w, 0));
  const y = Math.min(Math.max(cy - h / 2, FULL_BOX.y), Math.max(FULL_BOX.h - h, 0));
  return { x, y, w: Math.min(w, FULL_BOX.w), h: Math.min(h, FULL_BOX.h) };
}

/** Bubble radius in screen pixels, by usable capacity: area follows capacity. */
export function bubbleRadius(capacityKwh: number, maxCapacityKwh: number): number {
  return 5 + 15 * Math.sqrt(capacityKwh / maxCapacityKwh);
}

export interface LabelSpot {
  /** Offset of the text anchor from the bubble centre, in pixels. */
  dx: number;
  dy: number;
  anchor: "start" | "middle" | "end";
}

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

const overlaps = (a: Rect, b: Rect) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/**
 * Chooses where each of the `labelled` names goes (in priority order) so that no two names, and no
 * name and a bubble, overlap. A name that fits nowhere gets no label. Every item counts as a bubble
 * to avoid. Everything is in screen pixels, relative to the same origin.
 */
export function placeLabels(
  items: readonly { name: string; x: number; y: number; radius: number; width: number }[],
  height = 15,
  gap = 4,
  labelled: readonly string[] = items.map((i) => i.name),
): Map<string, LabelSpot> {
  const bubbles = items.map((i) => ({ x: i.x - i.radius, y: i.y - i.radius, w: 2 * i.radius, h: 2 * i.radius }));
  const taken: Rect[] = [];
  const spots = new Map<string, LabelSpot>();
  for (const name of labelled) {
    const index = items.findIndex((i) => i.name === name);
    const item = items[index];
    if (!item) continue;
    const { x, y, radius: r, width: w } = item;
    const candidates: { rect: Rect; spot: LabelSpot }[] = [
      { rect: { x: x + r + gap, y: y - height / 2, w, h: height }, spot: { dx: r + gap, dy: 0, anchor: "start" } },
      { rect: { x: x - r - gap - w, y: y - height / 2, w, h: height }, spot: { dx: -(r + gap), dy: 0, anchor: "end" } },
      {
        rect: { x: x - w / 2, y: y - r - gap - height, w, h: height },
        spot: { dx: 0, dy: -(r + gap + height / 2), anchor: "middle" },
      },
      {
        rect: { x: x - w / 2, y: y + r + gap, w, h: height },
        spot: { dx: 0, dy: r + gap + height / 2, anchor: "middle" },
      },
    ];
    for (const { rect, spot } of candidates) {
      const blocked =
        taken.some((t) => overlaps(rect, t)) || bubbles.some((b, i) => i !== index && overlaps(rect, b));
      if (!blocked) {
        taken.push(rect);
        spots.set(item.name, spot);
        break;
      }
    }
  }
  return spots;
}
