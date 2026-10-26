import { describe, expect, it } from "vitest";
import { pivotRegionalHistory } from "./shape";

describe("pivotRegionalHistory", () => {
  it("puts the level and the inflow of each region on one date axis", () => {
    const history = pivotRegionalHistory([
      { region: "CENTRO", day: "2026-10-02", reservoirPct: 0.7, inflowPct: null },
      { region: "CENTRO", day: "2026-10-01", reservoirPct: 0.6, inflowPct: null },
      { region: "CENTRO", day: "2026-10-01", reservoirPct: null, inflowPct: 0.9 },
      { region: "VALLE", day: "2026-10-02", reservoirPct: 0.5, inflowPct: 1.2 },
    ]);
    expect(history.dates).toEqual(["2026-10-01", "2026-10-02"]);
    expect(history.regions["CENTRO"]).toEqual({ reservoirPct: [0.6, 0.7], inflowPct: [0.9, null] });
    expect(history.regions["VALLE"]).toEqual({ reservoirPct: [null, 0.5], inflowPct: [null, 1.2] });
  });

  it("is empty without rows", () => {
    expect(pivotRegionalHistory([])).toEqual({ dates: [], regions: {} });
  });
});
