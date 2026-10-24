import { jsonResponse, problem } from "@/lib/api";
import { getModelRun } from "@/lib/data";

export async function GET() {
  const run = await getModelRun();
  if (!run) return problem(404, "No training run yet", "The pipeline has not recorded a training run.");
  return jsonResponse(run);
}
