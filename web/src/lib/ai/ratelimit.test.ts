import { describe, expect, it } from "vitest";
import { clientKey, createMemoryLimiter, createPostgresLimiter } from "./ratelimit";

describe("memory limiter", () => {
  it("allows up to the limit and then refuses, with a retry time", async () => {
    let now = 1_000_000_000_000;
    const limiter = createMemoryLimiter(() => now);
    const results = [];
    for (let i = 0; i < 4; i++) results.push(await limiter.hit("a", 3, 600));
    expect(results.map((r) => r.allowed)).toEqual([true, true, true, false]);
    expect(results[0]?.remaining).toBe(2);
    expect(results[3]?.retryAfterSec).toBeGreaterThan(0);
    expect(results[3]?.retryAfterSec).toBeLessThanOrEqual(600);
    now += 601_000;
    expect((await limiter.hit("a", 3, 600)).allowed).toBe(true);
  });

  it("counts clients separately", async () => {
    const limiter = createMemoryLimiter(() => 0);
    await limiter.hit("a", 1, 60);
    expect((await limiter.hit("a", 1, 60)).allowed).toBe(false);
    expect((await limiter.hit("b", 1, 60)).allowed).toBe(true);
  });

  it("keeps different window lengths apart for the same key", async () => {
    const limiter = createMemoryLimiter(() => 0);
    await limiter.hit("a", 1, 60);
    expect((await limiter.hit("a", 1, 3600)).allowed).toBe(true);
  });
});

describe("postgres limiter", () => {
  it("uses the hit count returned by the upsert and cleans old windows only occasionally", async () => {
    const calls: string[] = [];
    const sql = async (strings: TemplateStringsArray) => {
      calls.push(strings.join("?"));
      return calls.length === 1 ? [{ hits: 13 }] : [];
    };
    const limiter = createPostgresLimiter(sql, () => 1_000_000_000_000, () => 0.5);
    const r = await limiter.hit("chat:abc", 12, 600);
    expect(r.allowed).toBe(false);
    expect(calls).toHaveLength(1);
    expect(calls[0]).toContain("ON CONFLICT");

    const cleaning = createPostgresLimiter(sql, () => 1_000_000_000_000, () => 0.001);
    await cleaning.hit("chat:abc", 12, 600);
    expect(calls.some((c) => c.includes("DELETE"))).toBe(true);
  });
});

describe("clientKey", () => {
  it("is stable, salted and never contains the address", async () => {
    const a = await clientKey("203.0.113.9", "salt");
    expect(a).toBe(await clientKey("203.0.113.9", "salt"));
    expect(a).not.toBe(await clientKey("203.0.113.9", "other"));
    expect(a).not.toContain("203");
    expect(a).toMatch(/^[0-9a-f]{24}$/);
  });
});
