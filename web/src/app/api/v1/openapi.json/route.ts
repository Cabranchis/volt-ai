import type { NextRequest } from "next/server";
import { FIXED_ENDPOINT_LIMIT, jsonResponse, limitClient } from "@/lib/api";
import { openApiDocument } from "@/lib/openapi";

export async function GET(request: NextRequest) {
  const limited = await limitClient(request, "openapi", FIXED_ENDPOINT_LIMIT);
  if (limited) return limited;
  return jsonResponse(openApiDocument);
}
