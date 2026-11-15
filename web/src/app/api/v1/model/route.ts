import type { NextRequest } from "next/server";
import { FIXED_ENDPOINT_LIMIT, jsonResponse, limitClient, problem } from "@/lib/api";
import { getModelRun } from "@/lib/data";

export async function GET(request: NextRequest) {
  const limited = await limitClient(request, "model", FIXED_ENDPOINT_LIMIT);
  if (limited) return limited;
  const run = await getModelRun();
  if (!run) return problem(404, "No training run yet", "The pipeline has not recorded a training run.");
  return jsonResponse(run);
}
