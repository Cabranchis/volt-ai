import type { NextRequest } from "next/server";
import { jsonResponse, problem } from "@/lib/api";
import { getForecast } from "@/lib/data";
import type { ForecastTarget } from "@/lib/data/types";

const TARGETS: Record<string, ForecastTarget> = {
  demand: "demand_kwh",
  price: "price_mean_cop_kwh",
};

export async function GET(_request: NextRequest, ctx: RouteContext<"/api/v1/forecasts/[target]">) {
  const { target } = await ctx.params;
  const resolved = TARGETS[target];
  if (!resolved) return problem(404, "Unknown target", `Use one of: ${Object.keys(TARGETS).join(", ")}.`);

  const forecast = await getForecast(resolved);
  if (!forecast) return problem(404, "No forecast yet", "The pipeline has not produced a forecast for this target.");
  return jsonResponse(forecast);
}
