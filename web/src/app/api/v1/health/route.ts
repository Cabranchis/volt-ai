import { jsonResponse } from "@/lib/api";
import { getHealth } from "@/lib/data";

/** Freshness per dataset and per series, so an outage of the pipeline is visible, not silent (UC-10). */
export async function GET() {
  const health = await getHealth();
  const failing = health.datasets.filter((d) => d.status === "error");
  return jsonResponse({ status: failing.length === 0 ? "ok" : "degraded", ...health }, { cache: false });
}
