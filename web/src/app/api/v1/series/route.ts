import type { NextRequest } from "next/server";
import { z } from "zod";
import { jsonResponse, limitClient, parseQuery, problem } from "@/lib/api";
import { getSeries } from "@/lib/data";
import { isoDate, SERIES_NAMES, seriesNameSchema } from "@/lib/data/types";

const MAX_SPAN_DAYS = 4000;
const MAX_NAMES = 8;
/** The history starts here: an earlier `from` asks for the same rows as this one. */
const HISTORY_START = "2018-01-01";

// Strict, so a caller cannot make every request a new cache entry by adding a parameter the route ignores.
const querySchema = z
  .object({
    names: z
      .string()
      .min(1)
      .transform((value) => value.split(",").map((n) => n.trim()))
      .pipe(z.array(seriesNameSchema).min(1).max(SERIES_NAMES.length)),
    from: isoDate.optional(),
    to: isoDate.optional(),
  })
  .strict();

const today = (): string => new Date().toISOString().slice(0, 10);

export async function GET(request: NextRequest) {
  const limited = await limitClient(request, "series");
  if (limited) return limited;
  const parsed = parseQuery(querySchema, request.nextUrl.searchParams);
  if (!parsed.ok) return parsed.response;
  // One entry per series in one order: the cached read is keyed by its arguments.
  const names = [...new Set(parsed.data.names)].sort();
  if (names.length > MAX_NAMES) return problem(400, "Too many series", `At most ${MAX_NAMES} series per request.`);

  const { from, to } = parsed.data;
  if (from && to) {
    const span = (Date.parse(to) - Date.parse(from)) / 86_400_000;
    if (span < 0) return problem(400, "Invalid range", "`from` must not be after `to`.");
    if (span > MAX_SPAN_DAYS) return problem(400, "Range too long", `At most ${MAX_SPAN_DAYS} days.`);
  }

  // A range that reaches past the data on either side is the same read as the whole history, so
  // it is clamped to it and shares one cache entry; the response is never larger than the history.
  const now = today();
  const start = from && from > HISTORY_START ? from : HISTORY_START;
  const end = to && to < now ? to : now;
  if (start > end) {
    return jsonResponse({ dates: [], series: Object.fromEntries(names.map((name) => [name, []])) });
  }
  return jsonResponse(await getSeries(names, start, end));
}
