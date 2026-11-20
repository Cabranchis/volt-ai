import type { NextRequest } from "next/server";
import { FIXED_ENDPOINT_LIMIT, jsonResponse, limitClient } from "@/lib/api";
import { getHealth, getTrackRecord } from "@/lib/data";
import { assessHealth, failureReason } from "@/lib/health";
import { assessLiveRecord } from "@/lib/live-watch";

/**
 * The live record is advice. A failure reading it must not take the health answer down with it,
 * because an outside monitor reads this endpoint: it becomes `null`, which the watchdog treats as
 * unknown.
 */
async function readLiveRecord() {
  try {
    const [demand, price] = await Promise.all([getTrackRecord("demand_kwh"), getTrackRecord("price_mean_cop_kwh")]);
    return { demand: assessLiveRecord(demand), price: assessLiveRecord(price) };
  } catch {
    return null;
  }
}

/**
 * Freshness per dataset and per series, and whether the platform is `ok`, `stale` (nothing failed
 * but the data or the forecast is older than the pipeline leaves it) or `degraded` (something is
 * broken now). The answer is always HTTP 200: a monitor reads the `status` word. Failure texts from
 * the pipeline are reduced to a reason code; they are not published.
 *
 * `liveRecord` says whether the band of each forecast covers what happened over the 28 days ending
 * on the last settled day (`verdict`: `ok`, `low` or `insufficient`), or `null` when it could not be read. It is advice
 * for the watchdog and does not change `status`.
 */
export async function GET(request: NextRequest) {
  const limited = await limitClient(request, "health", FIXED_ENDPOINT_LIMIT);
  if (limited) return limited;
  const [health, liveRecord] = await Promise.all([getHealth(), readLiveRecord()]);
  const assessment = assessHealth(health);
  const { datasets, ...rest } = health;
  return jsonResponse(
    {
      status: assessment.status,
      reasons: assessment.reasons,
      ages: assessment.ages,
      liveRecord,
      ...rest,
      datasets: datasets.map(({ detail, ...d }) => ({
        ...d,
        reason: d.status === "error" ? failureReason(detail) : null,
      })),
    },
    { cache: false },
  );
}
