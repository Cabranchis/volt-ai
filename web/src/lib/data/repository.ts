import { createFixtureRepository } from "./fixtures";
import type { Repository } from "./types";

let cached: Repository | undefined;

/** "database" when reads go to PostgreSQL, "snapshot" when they come from the bundled JSON fixtures. */
export type DataSourceKind = "database" | "snapshot";

export function dataSourceKind(env: Record<string, string | undefined> = process.env): DataSourceKind {
  return env.DATABASE_URL_READONLY && env.VOLTIA_DATA_SOURCE !== "fixtures" ? "database" : "snapshot";
}

/**
 * PostgreSQL when DATABASE_URL_READONLY is set, JSON fixtures otherwise.
 * VOLTIA_DATA_SOURCE=fixtures forces the snapshot (tests, previews). The choice is reported by
 * health().source and shown in the UI, so a snapshot is never presented as live data.
 */
export async function getRepository(): Promise<Repository> {
  if (cached) return cached;
  if (dataSourceKind() === "database") {
    const { createPostgresRepository, getSql } = await import("./postgres");
    cached = createPostgresRepository(getSql(process.env.DATABASE_URL_READONLY as string));
  } else {
    cached = createFixtureRepository();
  }
  return cached;
}
