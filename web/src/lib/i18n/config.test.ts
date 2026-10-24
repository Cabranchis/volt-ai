import { describe, expect, it } from "vitest";
import { defaultLocale, hasLocale, negotiateLocale, switchLocalePath } from "./config";
import { en } from "./en";
import { es } from "./es";
import { fmt } from "./fmt";

describe("negotiateLocale", () => {
  it("falls back to the default when the header is missing or unsupported", () => {
    expect(negotiateLocale(null)).toBe(defaultLocale);
    expect(negotiateLocale("fr-FR,fr;q=0.9")).toBe(defaultLocale);
  });

  it("honours quality weights, not header order", () => {
    expect(negotiateLocale("es-CO;q=0.4, en-US;q=0.9")).toBe("en");
    expect(negotiateLocale("en;q=0.2, es-MX;q=0.8")).toBe("es");
  });

  it("matches on the base language", () => {
    expect(negotiateLocale("en-GB")).toBe("en");
    expect(negotiateLocale("ES")).toBe("es");
  });

  it("ignores malformed weights", () => {
    expect(negotiateLocale("en;q=abc, es;q=0.5")).toBe("es");
  });
});

describe("switchLocalePath", () => {
  it("swaps the locale segment and keeps the rest", () => {
    expect(switchLocalePath("/es/price", "en")).toBe("/en/price");
    expect(switchLocalePath("/en", "es")).toBe("/es");
  });

  it("adds a locale to a path without one", () => {
    expect(switchLocalePath("/price", "en")).toBe("/en/price");
    expect(switchLocalePath("/", "es")).toBe("/es");
  });
});

describe("hasLocale", () => {
  it("accepts only supported locales", () => {
    expect(hasLocale("es")).toBe(true);
    expect(hasLocale("fr")).toBe(false);
    expect(hasLocale("")).toBe(false);
  });
});

describe("dictionaries", () => {
  const keys = (value: unknown, prefix = ""): string[] =>
    typeof value === "object" && value !== null && !Array.isArray(value)
      ? Object.entries(value).flatMap(([k, v]) => keys(v, `${prefix}${k}.`))
      : [prefix.slice(0, -1)];

  it("have exactly the same keys in both languages", () => {
    expect(keys(es).sort()).toEqual(keys(en).sort());
  });

  it("keep the same placeholders in both languages", () => {
    const placeholders = (text: string) => (text.match(/\{\w+\}/g) ?? []).sort();
    const walk = (a: unknown, b: unknown, path: string): void => {
      if (typeof a === "string" && typeof b === "string") {
        expect(placeholders(b), path).toEqual(placeholders(a));
      } else if (typeof a === "object" && a !== null && typeof b === "object" && b !== null) {
        for (const key of Object.keys(a)) walk((a as Record<string, unknown>)[key], (b as Record<string, unknown>)[key], `${path}.${key}`);
      }
    };
    walk(en, es, "dict");
  });
});

describe("fmt", () => {
  it("fills known tokens and leaves unknown ones visible", () => {
    expect(fmt("{a} and {b}", { a: 1 })).toBe("1 and {b}");
  });
});
