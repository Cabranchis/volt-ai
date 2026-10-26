import { describe, expect, it } from "vitest";
import { monthTickRule, zoomTickRule } from "./chart-utils";

describe("zoomTickRule", () => {
  it("uses the month rule for a long window", () => {
    const rule = zoomTickRule(0, 800);
    expect(rule(0, "2024-01-01")).toBe(monthTickRule(800)(0, "2024-01-01"));
    expect(rule(10, "2024-01-11")).toBe(false);
  });

  it("labels about six evenly spaced days in a short window, even with no month start in it", () => {
    const rule = zoomTickRule(100, 30); // 30 days, a label every 5
    const labelled = Array.from({ length: 30 }, (_, i) => 100 + i).filter((i) => rule(i, "2024-03-05"));
    expect(labelled).toEqual([100, 105, 110, 115, 120, 125]);
  });

  it("never asks for a label every 0 days on a very short window", () => {
    const rule = zoomTickRule(7, 3);
    expect([7, 8, 9].filter((i) => rule(i, "2024-03-05"))).toEqual([7, 8, 9]);
  });
});
