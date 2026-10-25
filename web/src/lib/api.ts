import type { NextRequest } from "next/server";
import { z } from "zod";
import { clientKey, getRateLimiter } from "@/lib/ai/ratelimit";

const API_LIMIT = 60;
const API_WINDOW_SEC = 60;

/**
 * Per-client limit for the endpoints whose arguments an anonymous caller can vary freely, which
 * would otherwise bypass the CDN cache and reach the database on every request. Answers 429, or
 * null to continue. A failing limiter lets the request through: the data call fails on its own
 * if the database is down.
 */
export async function limitClient(request: NextRequest, scope: string): Promise<Response | null> {
  try {
    const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
    const address = forwarded || request.headers.get("x-real-ip") || "unknown";
    const key = await clientKey(address, process.env.RATE_LIMIT_SALT ?? "voltia");
    const hit = await (await getRateLimiter()).hit(`api:${scope}:${key}`, API_LIMIT, API_WINDOW_SEC);
    if (hit.allowed) return null;
    const response = problem(429, "Too many requests", `At most ${API_LIMIT} requests per minute.`);
    response.headers.set("Retry-After", String(hit.retryAfterSec));
    return response;
  } catch {
    return null;
  }
}

/** Responses are shared by every visitor and change once a day, so the CDN may keep them for an hour. */
const CACHE_CONTROL = "public, s-maxage=3600, stale-while-revalidate=86400";

export function jsonResponse(data: unknown, init: { status?: number; cache?: boolean } = {}): Response {
  return Response.json(data, {
    status: init.status ?? 200,
    headers: {
      "Cache-Control": init.cache === false ? "no-store" : CACHE_CONTROL,
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export function problem(status: number, title: string, detail?: string): Response {
  return Response.json(
    { type: "about:blank", title, status, ...(detail ? { detail } : {}) },
    { status, headers: { "Content-Type": "application/problem+json", "Cache-Control": "no-store" } },
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
