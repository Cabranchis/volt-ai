import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { es } from "@/lib/i18n/es";
import { scoreTrackRecord } from "@/lib/track-record";
import { TrackRecordPanel } from "./TrackRecordPanel";

const settled = scoreTrackRecord([
  { origin: "2026-10-01", day: "2026-10-02", horizon: 1, p10: 90, p50: 110, p90: 130, actual: 100, naive: 120 },
  { origin: "2026-10-01", day: "2026-10-09", horizon: 8, p10: 90, p50: 100, p90: 110, actual: 130, naive: 100 },
  { origin: "2026-10-01", day: "2026-10-30", horizon: 29, p10: 90, p50: 100, p90: 110, actual: null, naive: 100 },
]);
const none = scoreTrackRecord([]);

describe("TrackRecordPanel", () => {
  it("says the record is still empty when nothing has settled", () => {
    const html = renderToStaticMarkup(
      <TrackRecordPanel
        locale="es"
        dict={es.models}
        entries={[{ key: "price", title: es.models.targetPrice, record: none }]}
      />,
    );
    expect(html).toContain(es.models.live.empty);
    expect(html).not.toContain("<table");
  });

  it("shows the error against the reference and the coverage per horizon bucket", () => {
    const html = renderToStaticMarkup(
      <TrackRecordPanel
        locale="es"
        dict={es.models}
        entries={[
          { key: "demand", title: es.models.targetDemand, record: settled },
          { key: "price", title: es.models.targetPrice, record: none },
        ]}
      />,
    );
    expect(html).toContain("2 pronósticos evaluados");
    expect(html).toContain("Otros 1 esperan");
    expect(html).toContain("1 a 3 días");
    expect(html).toContain("8 a 14 días");
    expect(html).toContain("10,0 %"); // 10 % model error in the first bucket
    expect(html).toContain("20,0 %"); // 20 % reference error in the same bucket
    expect(html).toContain(es.models.live.naiveDemand);
    expect(html.match(/<table/g)).toHaveLength(1); // the price has nothing settled, so no table
  });
});
