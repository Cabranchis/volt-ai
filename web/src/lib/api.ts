import { z } from "zod";

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
