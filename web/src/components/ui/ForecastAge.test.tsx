// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ForecastAge } from "./ForecastAge";

const labels = { issued: "Forecast issued {when}", old: "older than usual, {days} days" };

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("ForecastAge", () => {
  it("says when the forecast was issued, without a warning while it is recent", () => {
    vi.useFakeTimers({ now: new Date("2026-11-15T15:00:00Z") });
    render(<ForecastAge issuedAt="2026-11-15T14:00:00Z" locale="en" labels={labels} />);
    expect(screen.getByText(/Forecast issued today/)).toBeInTheDocument();
    expect(screen.queryByText(/older than usual/)).not.toBeInTheDocument();
  });

  it("still counts two days as normal, and warns from the third", () => {
    vi.useFakeTimers({ now: new Date("2026-11-17T15:00:00Z") });
    const { unmount } = render(<ForecastAge issuedAt="2026-11-15T14:00:00Z" locale="en" labels={labels} />);
    expect(screen.queryByText(/older than usual/)).not.toBeInTheDocument();
    unmount();
    vi.setSystemTime(new Date("2026-11-18T15:00:00Z"));
    render(<ForecastAge issuedAt="2026-11-15T14:00:00Z" locale="en" labels={labels} />);
    expect(screen.getByText(/older than usual, 3 days/)).toBeInTheDocument();
  });
});
