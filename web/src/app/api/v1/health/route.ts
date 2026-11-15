import type { NextRequest } from "next/server";
import { FIXED_ENDPOINT_LIMIT, jsonResponse, limitClient } from "@/lib/api";
import { getHealth } from "@/lib/data";
import { assessHealth, failureReason } from "@/lib/health";

/**
 * Freshness per dataset and per series, and whether the platform is `ok`, `stale` (nothing failed
 * but the data or the forecast is older than the pipeline leaves it) or `degraded` (something is
 * broken now). The answer is always HTTP 200: a monitor reads the `status` word. Failure texts from
 * the pipeline are reduced to a reason code; they are not published.
 */
export async function GET(request: NextRequest) {
  const limited = await limitClient(request, "health", FIXED_ENDPOINT_LIMIT);
  if (limited) return limited;
  const health = await getHealth();
  const assessment = assessHealth(health);
  const { datasets, ...rest } = health;
  return jsonResponse(
    {
      status: assessment.status,
      reasons: assessment.reasons,
      ages: assessment.ages,
      ...rest,
      datasets: datasets.map(({ detail, ...d }) => ({
        ...d,
        reason: d.status === "error" ? failureReason(detail) : null,
      })),
    },
    { cache: false },
  );
}
