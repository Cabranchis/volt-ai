import { describe, expect, it } from "vitest";
import { isTableUnavailable } from "./postgres";

describe("isTableUnavailable", () => {
  it("treats a missing table and a missing grant as a table that is not there yet", () => {
    expect(isTableUnavailable({ code: "42P01" })).toBe(true);
    expect(isTableUnavailable({ code: "42501" })).toBe(true);
  });

  it("lets every other error through, so a real failure is never turned into an empty page", () => {
    expect(isTableUnavailable({ code: "57014" })).toBe(false); // statement timeout
    expect(isTableUnavailable({ code: "08006" })).toBe(false); // connection failure
    expect(isTableUnavailable(new Error("boom"))).toBe(false);
    expect(isTableUnavailable(null)).toBe(false);
    expect(isTableUnavailable(undefined)).toBe(false);
  });
});
