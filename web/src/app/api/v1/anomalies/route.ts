import type { NextRequest } from "next/server";
import { z } from "zod";
import { jsonResponse, limitClient, parseQuery } from "@/lib/api";
import { getAnomalies } from "@/lib/data";
import { forecastTargetSchema } from "@/lib/data/types";

const querySchema = z.object({
  target: forecastTargetSchema.optional(),
  limit: z.coerce.number().int().min(1).max(200).default(50),
});

export async function GET(request: NextRequest) {
  const limited = await limitClient(request, "anomalies");
  if (limited) return limited;
  const parsed = parseQuery(querySchema, request.nextUrl.searchParams);
  if (!parsed.ok) return parsed.response;
  return jsonResponse(await getAnomalies(parsed.data.limit, parsed.data.target));
}
