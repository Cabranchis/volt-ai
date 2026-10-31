import { createHash, timingSafeEqual } from "node:crypto";
import { revalidateTag } from "next/cache";
import type { NextRequest } from "next/server";
import { jsonResponse, limitClient, problem } from "@/lib/api";
import { DATA_TAG } from "@/lib/data";

/** Hash both sides so the comparison has equal lengths and does not leak where they differ. */
const digest = (value: string): Buffer => createHash("sha256").update(value).digest();

/**
 * Called by the daily pipeline when it ends: expires every cached read at once, so the next visitor
 * gets the new data instead of the old copy. Only the pipeline knows the token (REVALIDATE_TOKEN).
 */
export async function POST(request: NextRequest) {
  const expected = process.env.REVALIDATE_TOKEN;
  if (!expected) return problem(503, "Not configured");

  const limited = await limitClient(request, "revalidate");
  if (limited) return limited;

  const header = request.headers.get("authorization") ?? "";
  const token = header.startsWith("Bearer ") ? header.slice("Bearer ".length) : "";
  if (!timingSafeEqual(digest(token), digest(expected))) return problem(401, "Unauthorized");

  revalidateTag(DATA_TAG, { expire: 0 });
  return jsonResponse({ revalidated: true, at: new Date().toISOString() }, { cache: false });
}
