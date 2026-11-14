import snapshotText from "../public/snapshots/yangon-2015-2024-temperature.json?raw";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Analysis } from "./api/types";
import HistoricalDiscovery from "./components/HistoricalDiscovery";
import { ResultSummary, Cautions } from "./components/ResultPanels";
import { annualHistory, monthlyHistory, observationDifference } from "./lib/history";

function fixture(): Analysis {
  return JSON.parse(snapshotText) as Analysis;
}

describe("Historical Discovery evidence", () => {
  it("keeps missing annual slots and excluded values distinct, with calendar end-exclusive dates", () => {
    const a = fixture();
    a.period = { start: "2015-01-01", end_exclusive: "2018-01-01" };
    a.annual = [a.annual[0]!, { ...a.annual[2]!, eligible: false, value: 0, reasons: ["partial_calendar_year"] }];
    const rows = annualHistory(a);
    expect(rows.map((p) => p.date)).toEqual(["2015", "2016", "2017"]);
    expect(rows[1]).toMatchObject({ value: null, eligible: false, status: "No annual value" });
    expect(rows[2]).toMatchObject({ value: 0, eligible: false });
    expect(rows[2]!.status).toContain("Partial calendar year");
  });

  it("preserves omitted and rejected monthly values without interpolation", () => {
    const a = fixture();
    a.period = { start: "2015-01-01", end_exclusive: "2015-05-01" };
    a.series = [{ date: "2015-01-01", value: 0 }, { date: "2015-03-01", value: 9, usable: false, status: "insufficient_support" }];
    const rows = monthlyHistory(a);
    expect(rows.map((p) => p.value)).toEqual([0, null, null, null]);
    expect(rows[1]!.status).toBe("No observation returned");
    expect(rows[2]!.status).toContain("Insufficient monthly support");
    expect(observationDifference(rows[0], rows[1])).toBeNull();
  });

  it("compares observations in chosen order without converting a difference to a slope", () => {
    const rows = annualHistory(fixture());
    expect(observationDifference(rows[0], rows[1])).toBeCloseTo(rows[1]!.value! - rows[0]!.value!);
    expect(observationDifference(rows[0], rows[0])).toBe(0);
    expect(observationDifference(undefined, rows[0])).toBeNull();
  });

  it("switches resolutions and inspects a missing date by keyboard-compatible slider", async () => {
    const user = userEvent.setup();
    const a = fixture();
    a.series = [{ date: "2015-01-01", value: 23 }];
    render(<HistoricalDiscovery analysis={a} />);
    await user.click(screen.getByRole("button", { name: "Monthly observations" }));
    fireEvent.change(screen.getByRole("slider"), { target: { value: "1" } });
    const passport = screen.getByRole("region", { name: "Selected observation" });
    expect(within(passport).getByText("2015-02")).toBeInTheDocument();
    expect(within(passport).getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText("Comparison unavailable")).toBeInTheDocument();
    expect(screen.getByRole("slider")).toHaveAttribute("aria-valuetext", expect.stringContaining("No usable value"));
  });

  it("disables monthly mode when no monthly record is supplied", () => {
    render(<HistoricalDiscovery analysis={{ ...fixture(), series: [] }} />);
    expect(screen.getByRole("button", { name: "Monthly observations" })).toBeDisabled();
  });
});

describe("Mission Findings traceability", () => {
  it("exposes actual test values and links findings to observations", async () => {
    const a = fixture();
    render(<ResultSummary analysis={a} />);
    await userEvent.click(screen.getByText("Why do we say this?"));
    expect(screen.getByText(/Kendall: p = 1, alpha = 0.05/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Explore the supporting observations" })).toHaveAttribute("href", "#historical-discovery");
    expect(screen.getByText(/This is not a prediction interval/)).toBeInTheDocument();
  });

  it("does not manufacture inference for descriptive results", () => {
    const a = fixture();
    a.trend = { ...a.trend!, result_level: "descriptive_slope", mann_kendall: null, confidence_interval: null, significance_unavailable_reason: "Too few adjacent pairs" };
    render(<ResultSummary analysis={a} />);
    expect(screen.getByText(/Test not reported: Too few adjacent pairs/)).toBeInTheDocument();
    expect(screen.getAllByText("Descriptive slope only").length).toBeGreaterThan(0);
  });

  it("always explains causality and forecasting limits regardless of caveat ordering", () => {
    render(<Cautions analysis={{ ...fixture(), caveats: ["Other note", "Unrelated caveat"] }} />);
    expect(screen.getByText(/It is not a forecast, does not identify a cause/)).toBeInTheDocument();
  });
});
