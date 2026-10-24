import { createFixtureRepository } from "./fixtures";
import type { Repository } from "./types";

let cached: Repository | undefined;

/**
 * PostgreSQL when DATABASE_URL_READONLY is set, JSON fixtures otherwise.
 * VOLTIA_DATA_SOURCE=fixtures forces the snapshot (tests, previews). The choice is reported by
 * health().source and shown in the UI, so a snapshot is never presented as live data.
 */
export async function getRepository(): Promise<Repository> {
  if (cached) return cached;
  const url = process.env.DATABASE_URL_READONLY;
  if (url && process.env.VOLTIA_DATA_SOURCE !== "fixtures") {
    const { createPostgresRepository, getSql } = await import("./postgres");
    cached = createPostgresRepository(getSql(url));
  } else {
    cached = createFixtureRepository();
  }
  return cached;
}
