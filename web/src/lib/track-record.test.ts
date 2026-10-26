import { describe, expect, it } from "vitest";
import type { TrackRow } from "./data/types";
import { scoreTrackRecord } from "./track-record";

const row = (over: Partial<TrackRow>): TrackRow => ({
  origin: "2026-10-01",
  day: "2026-10-02",
  horizon: 1,
  p10: 90,
  p50: 100,
  p90: 110,
  actual: 100,
  naive: 100,
  ...over,
});

describe("scoreTrackRecord", () => {
  it("is empty when nothing has settled", () => {
    const record = scoreTrackRecord([row({ actual: null }), row({ actual: null, horizon: 2 })]);
    expect(record.scored).toBe(0);
    expect(record.pending).toBe(2);
    expect(record.overall).toBeNull();
    expect(record.buckets).toEqual([]);
    expect(record.winShare).toBeNull();
  });

  it("scores error, naive error and coverage per horizon bucket", () => {
    const record = scoreTrackRecord([
      row({ horizon: 1, p50: 110, actual: 100, naive: 120 }), // model 10 %, naive 20 %, inside
      row({ horizon: 3, p50: 100, actual: 100, naive: 90, day: "2026-10-04" }), // model 0 %, naive 10 %
      row({ horizon: 9, p50: 100, actual: 130, naive: 100, day: "2026-10-10" }), // outside the band
      row({ horizon: 2, actual: null }), // not settled
    ]);
    expect(record.scored).toBe(3);
    expect(record.pending).toBe(1);
    expect(record.firstDay).toBe("2026-10-02");
    expect(record.lastDay).toBe("2026-10-10");
    const [short, long] = record.buckets;
    expect([short?.from, short?.to, short?.n]).toEqual([1, 3, 2]);
    expect(short?.mape).toBeCloseTo(5, 6);
    expect(short?.naiveMape).toBeCloseTo(15, 6);
    expect(short?.coverage).toBe(1);
    expect([long?.from, long?.to, long?.n]).toEqual([8, 14, 1]);
    expect(long?.coverage).toBe(0);
    expect(record.overall?.n).toBe(3);
    expect(record.winShare).toBeCloseTo(2 / 3, 6);
  });

  it("ignores rows without a usable outcome and tolerates a missing reference", () => {
    const record = scoreTrackRecord([row({ actual: 0 }), row({ naive: null, p50: 105 })]);
    expect(record.scored).toBe(1);
    expect(record.buckets[0]?.naiveMape).toBeNull();
    expect(record.winShare).toBeNull();
  });
});
