import { describe, expect, it } from "vitest";
import type { TrackRow } from "./data/types";
import { assessLiveRecord, LOW_COVERAGE, MIN_SCORED_DAYS, WINDOW_DAYS } from "./live-watch";

const day = (offset: number): string => new Date(Date.parse("2026-10-01T00:00:00Z") + offset * 86_400_000).toISOString().slice(0, 10);

/** One forecast whose band is 90 to 110 and whose outcome is `actual`. */
const row = (offset: number, actual: number | null, origin = 0): TrackRow => ({
  origin: day(offset - origin - 1),
  day: day(offset),
  horizon: origin + 1,
  p10: 90,
  p50: 100,
  p90: 110,
  actual,
  naive: 100,
});

/** `n` consecutive days, each with two forecasts, whose outcome is inside or outside the band. */
const run = (n: number, inside: (i: number) => boolean): TrackRow[] =>
  Array.from({ length: n }, (_, i) => [row(i, inside(i) ? 100 : 150, 0), row(i, inside(i) ? 100 : 150, 1)]).flat();

describe("assessLiveRecord", () => {
  it("says nothing without settled days", () => {
    expect(assessLiveRecord([]).verdict).toBe("insufficient");
    expect(assessLiveRecord([row(0, null)]).verdict).toBe("insufficient");
    expect(assessLiveRecord([row(0, null)]).coverage).toBeNull();
  });

  it("does not judge a window with too few settled days, however bad", () => {
    const result = assessLiveRecord(run(MIN_SCORED_DAYS - 1, () => false));
    expect(result.verdict).toBe("insufficient");
    expect(result.scoredDays).toBe(MIN_SCORED_DAYS - 1);
  });

  it("is ok when the band covers", () => {
    const result = assessLiveRecord(run(WINDOW_DAYS, (i) => i % 5 !== 0));
    expect(result.verdict).toBe("ok");
    expect(result.coverage).toBeCloseTo(22 / 28, 4);
  });

  it("reports a sustained miss", () => {
    const result = assessLiveRecord(run(WINDOW_DAYS, (i) => i % 2 === 0 && i % 4 !== 0));
    expect(result.coverage).toBeLessThan(LOW_COVERAGE);
    expect(result.verdict).toBe("low");
  });

  it("does not report one bad week inside a good month", () => {
    const result = assessLiveRecord(run(WINDOW_DAYS, (i) => i < 21));
    expect(result.coverage).toBeCloseTo(0.75, 2);
    expect(result.verdict).toBe("ok");
  });

  it("counts a day once however many forecasts it has", () => {
    // 27 good days with one forecast each and a final day with 20 forecasts, all outside: by forecast it
    // would read 0.57, by day it is 27/28.
    const good = run(27, () => true).filter((r) => r.horizon === 1);
    const bad = Array.from({ length: 20 }, (_, k) => row(27, 150, k));
    const result = assessLiveRecord([...good, ...bad]);
    expect(result.scoredDays).toBe(28);
    expect(result.coverage).toBeCloseTo(27 / 28, 4);
  });

  it("looks only at the last window, counted from the last settled day", () => {
    const old = run(10, () => false).map((r) => ({ ...r, day: day(-100 + Number(r.day.slice(-2))) }));
    const recent = run(WINDOW_DAYS, () => true);
    const result = assessLiveRecord([...old, ...recent]);
    expect(result.verdict).toBe("ok");
    expect(result.scoredDays).toBe(WINDOW_DAYS);
    expect(result.from).toBe(day(0));
    expect(result.to).toBe(day(WINDOW_DAYS - 1));
  });

  it("ignores forecasts for days XM has not settled", () => {
    const rows = [...run(WINDOW_DAYS, () => true), row(WINDOW_DAYS, null), row(WINDOW_DAYS + 1, null)];
    expect(assessLiveRecord(rows).to).toBe(day(WINDOW_DAYS - 1));
  });

  it("counts the edges of the band as inside", () => {
    const rows = Array.from({ length: MIN_SCORED_DAYS }, (_, i) => row(i, i % 2 === 0 ? 90 : 110));
    expect(assessLiveRecord(rows).coverage).toBe(1);
  });
});
