import type { NextRequest } from "next/server";
import { z } from "zod";
import { jsonResponse, limitClient, parseQuery, problem } from "@/lib/api";
import { getSeries } from "@/lib/data";
import { isoDate, SERIES_NAMES, seriesNameSchema } from "@/lib/data/types";

const MAX_SPAN_DAYS = 4000;

const querySchema = z.object({
  names: z
    .string()
    .min(1)
    .transform((value) => value.split(",").map((n) => n.trim()))
    .pipe(z.array(seriesNameSchema).min(1).max(SERIES_NAMES.length)),
  from: isoDate.optional(),
  to: isoDate.optional(),
});

export async function GET(request: NextRequest) {
  const limited = await limitClient(request, "series");
  if (limited) return limited;
  const parsed = parseQuery(querySchema, request.nextUrl.searchParams);
  if (!parsed.ok) return parsed.response;
  const { names, from, to } = parsed.data;

  if (from && to) {
    const span = (Date.parse(to) - Date.parse(from)) / 86_400_000;
    if (span < 0) return problem(400, "Invalid range", "`from` must not be after `to`.");
    if (span > MAX_SPAN_DAYS) return problem(400, "Range too long", `At most ${MAX_SPAN_DAYS} days.`);
  }

  return jsonResponse(await getSeries([...new Set(names)], from, to));
}
