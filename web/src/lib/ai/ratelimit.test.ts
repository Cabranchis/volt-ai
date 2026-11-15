import { describe, expect, it } from "vitest";
import { clientKey, clientKeyFor, createMemoryLimiter, createPostgresLimiter, limitUnit, rateLimitSalt } from "./ratelimit";

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

describe("rateLimitSalt and clientKeyFor", () => {
  it("prefers RATE_LIMIT_SALT, then the database URL, never a public constant when a secret exists", () => {
    expect(rateLimitSalt({ RATE_LIMIT_SALT: "s", DATABASE_URL_READONLY: "u" })).toBe("s");
    expect(rateLimitSalt({ DATABASE_URL_READONLY: "u" })).toBe("u");
    expect(rateLimitSalt({})).toBe("voltia-local-development");
  });

  it("uses the first forwarded address and the salt from the environment", async () => {
    const headers = new Headers({ "x-forwarded-for": "203.0.113.9, 10.0.0.1" });
    expect(await clientKeyFor(headers, { RATE_LIMIT_SALT: "salt" })).toBe(await clientKey("203.0.113.9", "salt"));
    expect(await clientKeyFor(headers, { RATE_LIMIT_SALT: "other" })).not.toBe(
      await clientKeyFor(headers, { RATE_LIMIT_SALT: "salt" }),
    );
    expect(await clientKeyFor(new Headers(), { RATE_LIMIT_SALT: "salt" })).toBe(await clientKey("unknown", "salt"));
  });
});

describe("limitUnit", () => {
  it("leaves an IPv4 address, and anything that is not an address, as it is", () => {
    expect(limitUnit("203.0.113.9")).toBe("203.0.113.9");
    expect(limitUnit("unknown")).toBe("unknown");
    expect(limitUnit(" 203.0.113.9 ")).toBe("203.0.113.9");
  });

  it("counts an IPv6 address by its /64, however it is written", () => {
    const unit = "2001:0db8:0000:0042::/64";
    expect(limitUnit("2001:db8:0:42:aaaa:bbbb:cccc:dddd")).toBe(unit);
    expect(limitUnit("2001:db8:0:42::1")).toBe(unit);
    expect(limitUnit("2001:DB8:0:42:0:0:0:ffff")).toBe(unit);
    expect(limitUnit("[2001:db8:0:42::7]")).toBe(unit);
    expect(limitUnit("2001:db8:0:42::1%eth0")).toBe(unit);
    expect(limitUnit("2001:db8:0:43::1")).not.toBe(unit);
    expect(limitUnit("::1")).toBe("0000:0000:0000:0000::/64");
  });

  it("counts an IPv4-mapped IPv6 address as the IPv4 address it carries", () => {
    expect(limitUnit("::ffff:203.0.113.9")).toBe("203.0.113.9");
  });

  it("keeps a malformed address as given instead of guessing", () => {
    expect(limitUnit("2001:db8:::1")).toBe("2001:db8:::1");
    expect(limitUnit("1:2:3:4:5:6:7:8:9")).toBe("1:2:3:4:5:6:7:8:9");
    expect(limitUnit("zz::1")).toBe("zz::1");
  });

  it("gives one client key to every address of a /64, and different keys to different ones", async () => {
    const key = (address: string) => clientKeyFor(new Headers({ "x-forwarded-for": address }), { RATE_LIMIT_SALT: "s" });
    expect(await key("2001:db8:0:42::1")).toBe(await key("2001:db8:0:42:dead:beef:0:2"));
    expect(await key("2001:db8:0:42::1")).not.toBe(await key("2001:db8:0:43::1"));
  });
});
