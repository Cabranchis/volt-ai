import type { NextRequest } from "next/server";
import { csvResponse, jsonResponse, problem } from "@/lib/api";
import { getForecast } from "@/lib/data";
import type { ForecastTarget } from "@/lib/data/types";

const TARGETS: Record<string, ForecastTarget> = {
  demand: "demand_kwh",
  price: "price_mean_cop_kwh",
};

export async function GET(request: NextRequest, ctx: RouteContext<"/api/v1/forecasts/[target]">) {
  const { target } = await ctx.params;
  const resolved = Object.hasOwn(TARGETS, target) ? TARGETS[target] : undefined;
  if (!resolved) return problem(404, "Unknown target", `Use one of: ${Object.keys(TARGETS).join(", ")}.`);

  const forecast = await getForecast(resolved);
  if (!forecast) return problem(404, "No forecast yet", "The pipeline has not produced a forecast for this target.");
  const format = request.nextUrl.searchParams.get("format");
  if (format === "csv") {
    const rows = forecast.points.map((p) => [p.day, p.horizon, p.p10, p.p50, p.p90]);
    return csvResponse(`voltia-${target}-forecast.csv`, ["date", "horizon", "p10", "p50", "p90"], rows);
  }
  if (format !== null && format !== "json") {
    return problem(400, "Unknown format", "Use format=json or format=csv.");
  }
  return jsonResponse(forecast);
}
