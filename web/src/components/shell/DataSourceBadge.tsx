import { getHealth } from "@/lib/data";
import type { Dictionary } from "@/lib/i18n/en";

/** Says where the numbers come from, so a saved snapshot is never mistaken for live data. */
export async function DataSourceBadge({ labels }: { labels: Dictionary["common"] }) {
  const health = await getHealth();
  const live = health.source === "postgres";
  return (
    <p className="flex items-center gap-2 text-xs text-muted" title={live ? undefined : labels.snapshotNote}>
      <span
        aria-hidden="true"
        className={["size-2 rounded-full", live ? "bg-good" : "bg-accent"].join(" ")}
      />
      {live ? labels.sourcePostgres : labels.sourceFixtures}
    </p>
  );
}
