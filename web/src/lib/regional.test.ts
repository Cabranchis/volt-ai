import { describe, expect, it } from "vitest";
import regionalJson from "./data/fixtures/regional.json";
import { regionalSchema } from "./data/types";
import { MAP_SIZE } from "./geo/colombia";
import { RESERVOIR_SITES } from "./geo/reservoirs";
import {
  bubbleRadius,
  convexHull,
  framing,
  FULL_BOX,
  placeLabels,
  placeReservoirs,
  projectPoint,
  summarise,
} from "./regional";

const data = regionalSchema.parse(regionalJson);

describe("projectPoint", () => {
  it("puts every known reservoir inside the map", () => {
    for (const [name, site] of Object.entries(RESERVOIR_SITES)) {
      const { x, y } = projectPoint(site.lat, site.lon);
      expect(x, name).toBeGreaterThan(0);
      expect(x, name).toBeLessThan(MAP_SIZE.width);
      expect(y, name).toBeGreaterThan(0);
      expect(y, name).toBeLessThan(MAP_SIZE.height);
    }
  });
  it("runs north up and east right", () => {
    expect(projectPoint(8, -75).y).toBeLessThan(projectPoint(2, -75).y);
    expect(projectPoint(5, -70).x).toBeGreaterThan(projectPoint(5, -77).x);
  });
});

describe("placeReservoirs", () => {
  it("places every reservoir of the fixture and keeps the level between 0 and 1", () => {
    const placed = placeReservoirs(data);
    expect(placed).toHaveLength(data.reservoirs.length);
    for (const r of placed) {
      expect(r.level).toBeGreaterThan(0);
      expect(r.level).toBeLessThanOrEqual(1);
    }
  });
  it("skips a reservoir without a known site or capacity", () => {
    const placed = placeReservoirs({
      ...data,
      reservoirs: [
        { name: "NUEVO", region: "CENTRO", volumeKwh: 1, capacityKwh: 2, weekAgoKwh: null },
        { name: "PENOL", region: "ANTIOQUIA", volumeKwh: 1, capacityKwh: 0, weekAgoKwh: null },
      ],
    });
    expect(placed).toEqual([]);
  });
});

describe("summarise", () => {
  it("adds volumes and capacities, not percentages", () => {
    const placed = placeReservoirs(data);
    const summary = summarise(placed);
    const volume = placed.reduce((s, r) => s + r.volumeKwh, 0);
    const capacity = placed.reduce((s, r) => s + r.capacityKwh, 0);
    expect(summary?.level).toBeCloseTo(volume / capacity, 12);
    expect(summary?.weekChange).not.toBeNull();
  });
  it("has no week change when one reservoir lacks the older value", () => {
    const placed = placeReservoirs(data).map((r, i) => (i === 0 ? { ...r, weekAgoKwh: null } : r));
    expect(summarise(placed)?.weekChange).toBeNull();
    expect(summarise([])).toBeNull();
  });
});

describe("convexHull", () => {
  it("drops interior points", () => {
    const hull = convexHull([
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 0, y: 10 },
      { x: 5, y: 5 },
    ]);
    expect(hull).toHaveLength(4);
    expect(hull).not.toContainEqual({ x: 5, y: 5 });
  });
  it("returns what it is given when there are fewer than three points", () => {
    expect(convexHull([{ x: 1, y: 1 }])).toEqual([{ x: 1, y: 1 }]);
  });
});

describe("framing", () => {
  it("keeps the page's aspect ratio and stays inside the map", () => {
    const box = framing([{ x: 600, y: 500 }, { x: 700, y: 600 }], 100, 380);
    expect(box.w / box.h).toBeCloseTo(FULL_BOX.w / FULL_BOX.h, 6);
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.x + box.w).toBeLessThanOrEqual(FULL_BOX.w + 1e-6);
    expect(box.y + box.h).toBeLessThanOrEqual(FULL_BOX.h + 1e-6);
    expect(box.w).toBeGreaterThanOrEqual(380 - 1e-6);
  });
  it("shows the whole map when there is nothing to frame", () => {
    expect(framing([], 100, 380)).toEqual(FULL_BOX);
  });
});

describe("bubbleRadius", () => {
  it("grows with capacity and tops out at the largest reservoir", () => {
    expect(bubbleRadius(1, 4)).toBeLessThan(bubbleRadius(4, 4));
    expect(bubbleRadius(4, 4)).toBe(20);
  });
});

describe("placeLabels", () => {
  const item = (name: string, x: number, y: number) => ({ name, x, y, radius: 10, width: 80 });

  it("puts a lone name to the right of its bubble", () => {
    expect(placeLabels([item("A", 100, 100)]).get("A")).toEqual({ dx: 14, dy: 0, anchor: "start" });
  });

  it("moves a name out of the way of another name", () => {
    const spots = placeLabels([item("A", 100, 100), item("B", 100, 112)]);
    expect(spots.get("A")?.anchor).toBe("start");
    const b = spots.get("B");
    expect(b).toBeDefined();
    expect(b).not.toEqual(spots.get("A"));
  });

  it("leaves a name out when it fits nowhere", () => {
    const crowd = [item("A", 100, 100)];
    for (let i = 0; i < 12; i++) crowd.push(item(`N${i}`, 100 + (i % 4) * 14 - 20, 100 + Math.floor(i / 4) * 14 - 14));
    const spots = placeLabels(crowd);
    expect(spots.size).toBeLessThan(crowd.length);
  });
});
