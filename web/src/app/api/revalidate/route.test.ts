import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { revalidateTag } = vi.hoisted(() => ({ revalidateTag: vi.fn() }));
vi.mock("next/cache", () => ({ cacheLife: () => undefined, cacheTag: () => undefined, revalidateTag }));

import { POST } from "./route";

const TOKEN = "a-long-random-token-for-tests-0123456789";
const call = (headers: Record<string, string> = {}) =>
  POST(new NextRequest("http://localhost/api/revalidate", { method: "POST", headers }));

describe("POST /api/revalidate", () => {
  beforeEach(() => {
    revalidateTag.mockClear();
    process.env.REVALIDATE_TOKEN = TOKEN;
  });
  afterEach(() => {
    delete process.env.REVALIDATE_TOKEN;
  });

  it("answers 503 when no token is configured, and expires nothing", async () => {
    delete process.env.REVALIDATE_TOKEN;
    const res = await call({ authorization: `Bearer ${TOKEN}` });
    expect(res.status).toBe(503);
    expect(revalidateTag).not.toHaveBeenCalled();
  });

  it.each([
    ["no header", {}],
    ["a wrong token", { authorization: "Bearer not-the-token" }],
    ["a token without the Bearer word", { authorization: TOKEN }],
    ["an empty bearer", { authorization: "Bearer " }],
  ])("answers 401 with %s, and expires nothing", async (_name, headers) => {
    const res = await call(headers);
    expect(res.status).toBe(401);
    expect(res.headers.get("content-type")).toContain("application/problem+json");
    expect(revalidateTag).not.toHaveBeenCalled();
  });

  it("expires the data tag at once with the right token", async () => {
    const res = await call({ authorization: `Bearer ${TOKEN}` });
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    const body = await res.json();
    expect(body.revalidated).toBe(true);
    expect(revalidateTag).toHaveBeenCalledExactlyOnceWith("data", { expire: 0 });
  });
});
