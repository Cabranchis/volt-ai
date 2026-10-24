import { describe, expect, it } from "vitest";
import { addDays, daysBetween, formatDate, formatGWh, formatNumber, formatPercent, formatSigned } from "./format";

describe("number formatting", () => {
  it("uses each locale's separators", () => {
    expect(formatNumber(1234.5, "en", 1)).toBe("1,234.5");
    expect(formatNumber(1234.5, "es", 1)).toBe("1.234,5"); // es-CO groups from four digits
    expect(formatNumber(12345.5, "es", 1)).toBe("12.345,5");
  });

  it("converts kWh to GWh", () => {
    expect(formatGWh(248_492_453.53, "en")).toBe("248.5");
    expect(formatGWh(248_492_453.53, "es")).toBe("248,5");
  });

  it("formats a fraction as a percentage", () => {
    expect(formatPercent(0.765, "en")).toBe("76.5 %");
    expect(formatPercent(0.765, "es", 0)).toBe("77 %");
  });

  it("signs deltas and never shows a signed zero", () => {
    expect(formatSigned(3.24, "en")).toBe("+3.2");
    expect(formatSigned(-1.4, "en")).toBe("−1.4");
    expect(formatSigned(0.001, "en")).toBe("0.0");
    expect(formatSigned(-0.001, "en")).toBe("0.0");
  });
});

describe("dates", () => {
  it("shows the same calendar day whatever the viewer's time zone", () => {
    expect(formatDate("2026-10-21", "en")).toBe("Oct 21, 2026");
    expect(formatDate("2026-01-01", "en", "short")).toBe("Jan 1");
  });

  it("does arithmetic on calendar days across month and year ends", () => {
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
    expect(addDays("2024-03-01", -1)).toBe("2024-02-29");
    expect(daysBetween("2026-10-21", "2026-10-24")).toBe(3);
    expect(daysBetween("2026-10-24", "2026-10-21")).toBe(-3);
  });
});
