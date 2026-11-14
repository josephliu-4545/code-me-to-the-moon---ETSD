import snapshotText from "../public/snapshots/yangon-2015-2024-temperature.json?raw";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Analysis, AnalysisRequest, DiscoveryContract, PeriodComparison } from "./api/types";
import PeriodComparisonPanel from "./components/PeriodComparisonPanel";
import { annualHistory, monthlyHistory } from "./lib/history";
import { discoveryHeadline, trendVerdict } from "./lib/verdict";

const REQUEST: AnalysisRequest = { variable: "temperature", latitude: 16.8661, longitude: 96.1951, startYear: 2015, endYear: 2025, mode: "point" };
const ID = "a".repeat(64);
function analysis(): Analysis {
  const a = JSON.parse(snapshotText) as Analysis;
  a.data_status = "cached_nasa_retrieval";
  a.discovery = {
    analysis_id: ID, contract_version: "discovery-1",
    history: { annual: [{ date: "2015", value: 0, eligible: true, status: "eligible", reasons: [] }], monthly: [{ date: "2015-01", value: null, eligible: false, status: "withheld", reasons: ["insufficient_support"] }], annual_units: "°C", monthly_units: "°C", monthly_available: true, interpolated: false, end_exclusive: "2025-01-01" },
    findings: { kind: "descriptive", label: "Descriptive slope only", inference: "Descriptive", note: "Server qualification", headline: "Server-derived finding", slope: .02, slope_units: "°C/year", per_decade: .2, per_decade_units: "°C/decade", fitted_change: .18, slope_method: "Theil-Sen slope", test_method: "Mann-Kendall", tested_null: "No monotonic trend", test_reported: false, test: null, confidence_interval: null, eligible_years: [2015, 2024], serial_dependence: null, limitations: ["Not causal"] },
  } satisfies DiscoveryContract;
  return a;
}
const RESULT: PeriodComparison = {
  analysis_id: ID,
  first: { start_year: 2015, end_year_inclusive: 2019, expected_years: 5, eligible_years: [2015, 2016, 2017, 2018, 2019], count: 5, mean: 27, excluded_years: [] },
  second: { start_year: 2020, end_year_inclusive: 2024, expected_years: 5, eligible_years: [2020, 2021, 2022, 2023, 2024], count: 5, mean: 28, excluded_years: [] },
  status: "available", difference: 1, units: "°C", annual_units: "°C", statistic: "Equal-weighted mean of eligible annual summaries; second period minus first period.", annual_value_definition: "annual mean of monthly means", warnings: ["Descriptive, not a significance test."], data_status: "cached_nasa_retrieval", cache: { hit: true, retrieved_at: "2026-11-14T00:00:00Z", age_seconds: 2 },
};
function renderPanel(a = analysis()) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><PeriodComparisonPanel analysis={a} request={REQUEST} /></QueryClientProvider>);
}
afterEach(() => vi.unstubAllGlobals());

describe("Backend-driven feature contracts", () => {
  it("uses server history and findings instead of recomputing conflicting interpretations", () => {
    const a = analysis();
    expect(annualHistory(a)).toHaveLength(1);
    expect(annualHistory(a)[0]!.value).toBe(0);
    expect(monthlyHistory(a)[0]!.value).toBeNull();
    expect(monthlyHistory(a)[0]!.status).toContain("Insufficient monthly support");
    expect(trendVerdict(a).kind).toBe("descriptive");
    expect(discoveryHeadline(a)).toBe("Server-derived finding");
  });
  it("requests backend period means with submitted location, dates and evidence identity", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(RESULT), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    renderPanel();
    await userEvent.click(screen.getByRole("button", { name: "Compare periods" }));
    expect(await screen.findByText("+1 °C")).toBeInTheDocument();
    const url = new URL(fetchMock.mock.calls[0]![0], "http://localhost");
    expect(url.pathname).toBe("/api/v2/period-comparison");
    expect(url.searchParams.get("analysis_id")).toBe(ID);
    expect(url.searchParams.get("first_end_year")).toBe("2019");
    expect(url.searchParams.get("second_start_year")).toBe("2020");
    expect(url.searchParams.get("latitude")).toBe("16.8661");
    expect(url.searchParams.get("end_date")).toBe("2025-01-01");
    await userEvent.selectOptions(screen.getByLabelText("First period through"), "2020");
    expect(screen.getByRole("button", { name: "Compare periods" })).toBeDisabled();
    expect(screen.queryByText("+1 °C")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("does not compare saved snapshots against a fresh live result", () => {
    const a = analysis(); a.data_status = "saved_snapshot";
    renderPanel(a);
    expect(screen.getByRole("button", { name: "Compare periods" })).toBeDisabled();
    expect(screen.getByText(/Saved snapshots and older API results remain available/)).toBeInTheDocument();
  });
  it("shows a changed-evidence error without displaying a numeric comparison", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { reason: "analysis_changed", message: "Run the investigation again." } }), { status: 409 })));
    renderPanel();
    await userEvent.click(screen.getByRole("button", { name: "Compare periods" }));
    expect(await screen.findByText("Investigation evidence changed")).toBeInTheDocument();
    expect(screen.queryByText("+1 °C")).not.toBeInTheDocument();
  });
});
