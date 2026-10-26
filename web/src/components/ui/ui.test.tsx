// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DataTable } from "./DataTable";
import { DriversChart } from "./DriversChart";
import { Freshness } from "./Freshness";
import { MixBar } from "./MixBar";
import { StatStrip } from "./StatStrip";
import { en } from "@/lib/i18n/en";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("DataTable", () => {
  it("is a real table with a caption and column headers, inside a closed disclosure", () => {
    render(
      <DataTable
        caption="Daily demand forecast"
        columns={[
          { key: "date", header: "Date" },
          { key: "p50", header: "P50", align: "right" },
        ]}
        rows={[{ date: "Oct 22", p50: "243.1" }]}
        showLabel="Show data table"
        hideLabel="Hide data table"
      />,
    );
    const table = screen.getByRole("table", { hidden: true });
    expect(within(table).getByRole("columnheader", { name: "P50", hidden: true })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "243.1", hidden: true })).toBeInTheDocument();
    expect(table.closest("details")).not.toHaveAttribute("open");
  });
});

describe("StatStrip", () => {
  it("shows each figure with its own date, and a direction word besides the arrow", () => {
    render(
      <StatStrip
        stats={[
          { label: "Demand", value: "245.3", unit: "GWh/day", delta: "+0.7 GWh/day vs 7 days earlier", deltaSign: 1, context: "on Oct 21, 2026" },
          { label: "ONI", value: "2.16", unit: "", note: "Strong El Niño", context: "season centred on Aug 2026" },
        ]}
      />,
    );
    expect(screen.getByText("Demand")).toBeInTheDocument();
    expect(screen.getByText("on Oct 21, 2026")).toBeInTheDocument();
    expect(screen.getByText("Strong El Niño")).toBeInTheDocument();
  });
});

describe("MixBar", () => {
  const shares = { thermal: 0.388, hydro: 0.551, wind: 0.001, solar: 0.05, cogen: 0.009, other: 0.001 };

  it("describes the bar in words and lists every source with its exact share", () => {
    render(<MixBar locale="en" shares={shares} yearAgo={{ ...shares, thermal: 0.1 }} labels={en.mix} yearAgoLabel="{share} a year ago" />);
    expect(screen.getByRole("img")).toHaveAccessibleName(/Thermal 39 %.*Hydro 55 %/);
    expect(screen.getByText("55.1 %")).toBeInTheDocument();
    expect(screen.getByText("10 % a year ago")).toBeInTheDocument();
  });
});

describe("DriversChart", () => {
  it("writes the sign and direction of each factor, not only the bar", () => {
    render(
      <DriversChart
        locale="en"
        scale={1e6}
        decimals={1}
        unit="GWh/day"
        color="demand"
        dict={en.drivers}
        drivers={[
          { feature: "is_holiday", contribution: -12_500_000, direction: "down" },
          { feature: "same_dow_last_rel", contribution: 3_200_000, direction: "up" },
        ]}
      />,
    );
    expect(screen.getByText("Public holiday")).toBeInTheDocument();
    expect(screen.getByText("−12.5")).toBeInTheDocument();
    expect(screen.getByText("+3.2")).toBeInTheDocument();
    expect(screen.getByLabelText("lowers")).toBeInTheDocument();
    expect(screen.getByLabelText("raises")).toBeInTheDocument();
  });
});

describe("Freshness", () => {
  const labels = { dataThrough: "Data through {date}", fresh: "Up to date", stale: "Data is {days} days old" };

  it("warns when the newest data is older than four days, judged against today in Bogotá", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-30T15:00:00Z"));
    render(<Freshness lastDay="2026-10-21" lastDayLabel="Oct 21" labels={labels} />);
    expect(screen.getByText(/Data through Oct 21 · Data is 9 days old/)).toBeInTheDocument();
  });

  it("stays quiet when the data is recent", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-23T15:00:00Z"));
    render(<Freshness lastDay="2026-10-21" lastDayLabel="Oct 21" labels={labels} />);
    expect(screen.getByText("Data through Oct 21")).toBeInTheDocument();
  });

  it("adds the newer series after the main date", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-23T15:00:00Z"));
    render(<Freshness lastDay="2026-10-21" lastDayLabel="Oct 21" labels={labels} detail="Hydrology through Oct 23" />);
    expect(screen.getByText("Data through Oct 21 · Hydrology through Oct 23")).toBeInTheDocument();
  });
});
