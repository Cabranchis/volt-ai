import type { NextRequest } from "next/server";
import { z } from "zod";
import { clientKeyFor, getRateLimiter } from "@/lib/ai/ratelimit";
import { dataSourceKind } from "@/lib/data/repository";

const API_LIMIT = 60;
/** Endpoints whose answer does not depend on the caller's arguments cost one cached read each. */
export const FIXED_ENDPOINT_LIMIT = 120;
const API_WINDOW_SEC = 60;

/**
 * Per-client limit for the endpoints whose arguments an anonymous caller can vary freely, which
 * would otherwise bypass the CDN cache and reach the database on every request. Answers 429, or
 * null to continue. A failing limiter lets the request through: the data call fails on its own
 * if the database is down.
 */
export async function limitClient(
  request: NextRequest,
  scope: string,
  limit: number = API_LIMIT,
): Promise<Response | null> {
  try {
    const key = await clientKeyFor(request.headers);
    const hit = await (await getRateLimiter()).hit(`api:${scope}:${key}`, limit, API_WINDOW_SEC);
    if (hit.allowed) return null;
    const response = problem(429, "Too many requests", `At most ${limit} requests per minute.`);
    response.headers.set("Retry-After", String(hit.retryAfterSec));
    return response;
  } catch {
    return null;
  }
}

/**
 * Responses are shared by every visitor and the data changes a few times a day. The CDN keeps them
 * for five minutes and may serve an older copy for ten more while it refreshes, so a day that the
 * pipeline has just published reaches the API within a quarter of an hour, not a day.
 */
const CACHE_CONTROL = "public, s-maxage=300, stale-while-revalidate=600";

/** Where this deployment reads its data from: a response from a snapshot is never mistaken for live data. */
const sourceHeader = (): Record<string, string> => ({ "X-Data-Source": dataSourceKind() });

export function jsonResponse(data: unknown, init: { status?: number; cache?: boolean } = {}): Response {
  return Response.json(data, {
    status: init.status ?? 200,
    headers: {
      "Cache-Control": init.cache === false ? "no-store" : CACHE_CONTROL,
      "X-Content-Type-Options": "nosniff",
      ...sourceHeader(),
    },
  });
}

/**
 * A CSV download for spreadsheets: comma-separated, "." decimals, a byte-order mark so Excel
 * reads the file as UTF-8. Cells that start with a formula character are neutralised.
 */
export function csvResponse(
  filename: string,
  header: readonly string[],
  rows: readonly (readonly (string | number | null)[])[],
): Response {
  const cell = (value: string | number | null): string => {
    if (value === null) return "";
    const text = String(value);
    const safe = /^[=+\-@\t\r]/.test(text) && typeof value === "string" ? `'${text}` : text;
    return /[",\n\r]/.test(safe) ? `"${safe.replaceAll('"', '""')}"` : safe;
  };
  const body = [header, ...rows].map((row) => row.map(cell).join(",")).join("\r\n");
  return new Response(`﻿${body}\r\n`, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${filename}"`,
      "Cache-Control": CACHE_CONTROL,
      "X-Content-Type-Options": "nosniff",
      ...sourceHeader(),
    },
  });
}

export function problem(status: number, title: string, detail?: string): Response {
  return Response.json(
    { type: "about:blank", title, status, ...(detail ? { detail } : {}) },
    {
      status,
      headers: { "Content-Type": "application/problem+json", "Cache-Control": "no-store", ...sourceHeader() },
    },
  );
}

/** Validate query parameters, answering 400 with the reason instead of throwing. */
export function parseQuery<T extends z.ZodType>(
  schema: T,
  searchParams: URLSearchParams,
): { ok: true; data: z.infer<T> } | { ok: false; response: Response } {
  const result = schema.safeParse(Object.fromEntries(searchParams));
  if (result.success) return { ok: true, data: result.data };
  const detail = result.error.issues.map((i) => `${i.path.join(".") || "query"}: ${i.message}`).join("; ");
  return { ok: false, response: problem(400, "Invalid query parameters", detail) };
}
