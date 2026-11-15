import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";
import { GET as anomalies } from "@/app/api/v1/anomalies/route";
import { GET as forecasts } from "@/app/api/v1/forecasts/[target]/route";
import { GET as health } from "@/app/api/v1/health/route";
import { GET as model } from "@/app/api/v1/model/route";
import { GET as openapi } from "@/app/api/v1/openapi.json/route";
import { GET as series } from "@/app/api/v1/series/route";
import { SERIES_NAMES } from "@/lib/data/types";

const get = (path: string) => new NextRequest(`http://localhost${path}`);

describe("GET /api/v1/series", () => {
  it("returns columns for the requested series and range", async () => {
    const res = await series(get("/api/v1/series?names=demand_kwh,price_mean_cop_kwh&from=2026-10-01&to=2026-10-05"));
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toContain("s-maxage=300");
    expect(res.headers.get("x-data-source")).toBe("snapshot");
    const body = await res.json();
    expect(body.dates).toEqual(["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05"]);
    expect(Object.keys(body.series)).toEqual(["demand_kwh", "price_mean_cop_kwh"]);
    expect(body.series.demand_kwh).toHaveLength(5);
  });

  it.each([
    ["no names", "/api/v1/series"],
    ["unknown series", "/api/v1/series?names=drop_table"],
    ["bad date", "/api/v1/series?names=demand_kwh&from=yesterday"],
    ["reversed range", "/api/v1/series?names=demand_kwh&from=2026-10-05&to=2026-10-01"],
    ["month 13", "/api/v1/series?names=demand_kwh&from=2026-13-01"],
    ["30 February", "/api/v1/series?names=demand_kwh&from=2026-02-30"],
    ["range over the cap", "/api/v1/series?names=demand_kwh&from=2000-01-01&to=2026-10-01"],
    ["a parameter the route does not know", "/api/v1/series?names=demand_kwh&cachebuster=1"],
    ["more than 8 series", `/api/v1/series?names=${SERIES_NAMES.slice(0, 9).join(",")}`],
  ])("rejects %s with a problem document", async (_name, path) => {
    const res = await series(get(path));
    expect(res.status).toBe(400);
    expect(res.headers.get("content-type")).toContain("application/problem+json");
    expect(res.headers.get("cache-control")).toBe("no-store");
  });

  it("answers the same read for the same series in any order, and for a range that reaches past the data", async () => {
    const a = await (await series(get("/api/v1/series?names=price_mean_cop_kwh,demand_kwh&from=2026-10-01&to=2026-10-03"))).json();
    const b = await (await series(get("/api/v1/series?names=demand_kwh,price_mean_cop_kwh,demand_kwh&from=2026-10-01&to=2026-10-03"))).json();
    expect(b).toEqual(a);
    const exact = await (await series(get("/api/v1/series?names=demand_kwh&from=2018-01-01&to=2020-12-31"))).json();
    const early = await (await series(get("/api/v1/series?names=demand_kwh&from=2015-01-01&to=2020-12-31"))).json();
    expect(early.dates[0]).toBe("2018-01-01");
    expect(early).toEqual(exact);
  });

  it("answers a range entirely outside the history with one empty frame, not a new read", async () => {
    for (const range of ["from=2031-05-05", "from=2031-06-06", "to=2016-01-01&from=2015-01-01"]) {
      const body = await (await series(get(`/api/v1/series?names=demand_kwh&${range}`))).json();
      expect(body).toEqual({ dates: [], series: { demand_kwh: [] } });
    }
  });

  it("rejects SQL-looking input instead of passing it on", async () => {
    const res = await series(get("/api/v1/series?names=" + encodeURIComponent("demand_kwh';DROP TABLE series_daily;--")));
    expect(res.status).toBe(400);
  });
});

describe("GET /api/v1/forecasts/{target}", () => {
  it("404s on an unknown target", async () => {
    const res = await forecasts(get("/api/v1/forecasts/gas"), { params: Promise.resolve({ target: "gas" }) } as never);
    expect(res.status).toBe(404);
  });

  it("marks where the data comes from", async () => {
    const res = await forecasts(get("/api/v1/forecasts/price"), { params: Promise.resolve({ target: "price" }) } as never);
    expect(res.headers.get("x-data-source")).toBe("snapshot");
  });

  it.each(["constructor", "toString", "__proto__"])("404s on the object property %s", async (target) => {
    const res = await forecasts(get(`/api/v1/forecasts/${target}`), { params: Promise.resolve({ target }) } as never);
    expect(res.status).toBe(404);
  });
});

describe("GET /api/v1/anomalies", () => {
  it("validates limit and target", async () => {
    expect((await anomalies(get("/api/v1/anomalies?limit=1000"))).status).toBe(400);
    expect((await anomalies(get("/api/v1/anomalies?target=gas"))).status).toBe(400);
    expect((await anomalies(get("/api/v1/anomalies?limit=5"))).status).toBe(200);
  });
});

describe("GET /api/v1/health", () => {
  it("reports freshness per series and says where the data comes from", async () => {
    const body = await (await health(get("/api/v1/health"))).json();
    expect(body.source).toBe("fixtures");
    expect(["ok", "stale", "degraded"]).toContain(body.status);
    expect(Array.isArray(body.reasons)).toBe(true);
    expect(body.ages).toHaveProperty("dataDays");
    // Failure texts are never published, only a reason code.
    expect(JSON.stringify(body)).not.toContain("detail");
    expect(body.series.find((s: { series: string }) => s.series === "demand_kwh")?.lastDay).toMatch(/^2026-/);
  });
});

describe("GET /api/v1/model", () => {
  it("answers 404 until a training run exists, 200 afterwards", async () => {
    expect([200, 404]).toContain((await model(get("/api/v1/model"))).status);
  });
});

describe("OpenAPI document", () => {
  it("describes every route that exists and every series name", async () => {
    const doc = await (await openapi(get("/api/v1/openapi.json"))).json();
    expect(doc.openapi).toBe("3.1.0");
    expect(Object.keys(doc.paths).sort()).toEqual(["/anomalies", "/forecasts/{target}", "/health", "/model", "/series"]);
    for (const name of SERIES_NAMES) {
      expect(doc.components.schemas.SeriesFrame.properties.series.description).toContain(name);
    }
  });
});

describe("per-client limit on the open-ended endpoints", () => {
  it("answers 429 with Retry-After after 60 requests a minute from one address", async () => {
    const call = () =>
      anomalies(new NextRequest("http://localhost/api/v1/anomalies?limit=1", { headers: { "x-forwarded-for": "203.0.113.9" } }));
    let last = 200;
    let retryAfter: string | null = null;
    for (let i = 0; i < 61; i++) {
      const res = await call();
      last = res.status;
      retryAfter = res.headers.get("retry-after");
    }
    expect(last).toBe(429);
    expect(Number(retryAfter)).toBeGreaterThan(0);
    const other = await anomalies(
      new NextRequest("http://localhost/api/v1/anomalies?limit=1", { headers: { "x-forwarded-for": "203.0.113.10" } }),
    );
    expect(other.status).toBe(200);
  });
});

describe("GET /api/v1/forecasts/{target}?format=csv", () => {
  it("downloads the forecast as a spreadsheet-friendly file", async () => {
    const res = await forecasts(get("/api/v1/forecasts/demand?format=csv"), { params: Promise.resolve({ target: "demand" }) } as never);
    expect([200, 404]).toContain(res.status);
    if (res.status === 200) {
      expect(res.headers.get("content-type")).toContain("text/csv");
      expect(res.headers.get("content-disposition")).toContain("voltia-demand-forecast.csv");
      const bytes = new Uint8Array(await res.clone().arrayBuffer());
      expect([...bytes.slice(0, 3)]).toEqual([0xef, 0xbb, 0xbf]); // a BOM, so Excel reads UTF-8
      const text = await res.text();
      expect(text.startsWith("date,horizon,p10,p50,p90\r\n")).toBe(true);
      expect(text.trim().split("\r\n").length).toBeGreaterThan(1);
    }
  });

  it("rejects an unknown format", async () => {
    const res = await forecasts(get("/api/v1/forecasts/demand?format=xml"), { params: Promise.resolve({ target: "demand" }) } as never);
    expect([400, 404]).toContain(res.status);
  });
});

describe("per-client limit on the endpoints with fixed answers", () => {
  it("allows 120 requests a minute from one address and then answers 429", async () => {
    const call = () =>
      openapi(new NextRequest("http://localhost/api/v1/openapi.json", { headers: { "x-forwarded-for": "203.0.113.77" } }));
    let last = 200;
    for (let i = 0; i < 121; i++) last = (await call()).status;
    expect(last).toBe(429);
  });
});
