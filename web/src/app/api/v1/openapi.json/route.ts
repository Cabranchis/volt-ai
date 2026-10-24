import { jsonResponse } from "@/lib/api";
import { openApiDocument } from "@/lib/openapi";

export function GET() {
  return jsonResponse(openApiDocument);
}
