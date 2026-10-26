export interface RateResult {
  allowed: boolean;
  remaining: number;
  retryAfterSec: number;
}

export interface RateLimiter {
  /** Count one hit for `key` in the current fixed window and say whether it is within `limit`. */
  hit(key: string, limit: number, windowSec: number): Promise<RateResult>;
}

const result = (count: number, limit: number, windowSec: number, nowSec: number): RateResult => {
  const windowStart = Math.floor(nowSec / windowSec) * windowSec;
  return {
    allowed: count <= limit,
    remaining: Math.max(limit - count, 0),
    retryAfterSec: Math.max(windowStart + windowSec - nowSec, 1),
  };
};

/** Per-instance limiter. Used for local development and when no database is configured. */
export function createMemoryLimiter(now: () => number = Date.now): RateLimiter {
  const counters = new Map<string, { windowStart: number; count: number }>();
  return {
    async hit(key, limit, windowSec) {
      const nowSec = Math.floor(now() / 1000);
      const windowStart = Math.floor(nowSec / windowSec) * windowSec;
      const bucket = `${key}:${windowSec}`;
      const current = counters.get(bucket);
      const count = current && current.windowStart === windowStart ? current.count + 1 : 1;
      counters.set(bucket, { windowStart, count });
      if (counters.size > 5000) {
        for (const [k, v] of counters) if (v.windowStart < windowStart - windowSec) counters.delete(k);
      }
      return result(count, limit, windowSec, nowSec);
    },
  };
}

interface SqlLike {
  (strings: TemplateStringsArray, ...values: unknown[]): PromiseLike<Record<string, unknown>[]>;
}

/**
 * Database-backed limiter, shared by every serverless instance. The web role may write only the
 * rate_limits table (db/migrations/0002_roles.pg.sql). Old windows are removed now and then.
 */
export function createPostgresLimiter(sql: SqlLike, now: () => number = Date.now, random = Math.random): RateLimiter {
  return {
    async hit(key, limit, windowSec) {
      const nowSec = Math.floor(now() / 1000);
      const windowStart = Math.floor(nowSec / windowSec) * windowSec;
      const bucket = `${key}:${windowSec}`;
      const rows = await sql`
        INSERT INTO rate_limits (client_key, window_start, hits)
        VALUES (${bucket}, ${windowStart}, 1)
        ON CONFLICT (client_key, window_start) DO UPDATE SET hits = rate_limits.hits + 1
        RETURNING hits`;
      if (random() < 0.02) {
        await sql`DELETE FROM rate_limits WHERE window_start < ${nowSec - 2 * 86_400}`;
      }
      return result(Number(rows[0]?.["hits"] ?? 1), limit, windowSec, nowSec);
    },
  };
}

/** SHA-256 of salt + address, so the database never stores a visitor's IP. */
export async function clientKey(address: string, salt: string): Promise<string> {
  const data = new TextEncoder().encode(`${salt}|${address}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)]
    .slice(0, 12)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * The salt that keeps a stored key from being reversed by trying every IPv4 address. It comes from
 * RATE_LIMIT_SALT; when that is missing it falls back to a secret every deployment already has (the
 * database URL), so the key is never hashed with a value anyone can read in the repository.
 */
export function rateLimitSalt(env: Record<string, string | undefined> = process.env): string {
  return env.RATE_LIMIT_SALT || env.DATABASE_URL_READONLY || "voltia-local-development";
}

/** The caller's key for the rate limiters: the first address Vercel reports, hashed with the salt. */
export async function clientKeyFor(
  headers: Headers,
  env: Record<string, string | undefined> = process.env,
): Promise<string> {
  const forwarded = headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  const address = forwarded || headers.get("x-real-ip") || "unknown";
  return clientKey(address, rateLimitSalt(env));
}

let shared: Promise<RateLimiter> | undefined;

export function getRateLimiter(): Promise<RateLimiter> {
  shared ??= (async () => {
    const url = process.env.DATABASE_URL_READONLY;
    if (url && process.env.VOLTIA_DATA_SOURCE !== "fixtures") {
      const { getSql } = await import("@/lib/data/postgres");
      return createPostgresLimiter(getSql(url) as unknown as SqlLike);
    }
    return createMemoryLimiter();
  })();
  return shared;
}
