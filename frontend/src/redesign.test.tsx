import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Analysis } from "./api/types";
import { ResultSummary } from "./components/ResultPanels";
import CiRuler from "./components/science/CiRuler";
import MonthMatrix from "./components/science/MonthMatrix";
import { calendarSeries, gapRuns } from "./lib/series";
import { trendVerdict } from "./lib/verdict";

function base(overrides: Partial<Analysis> = {}): Analysis {
  const years = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024];
  return {
    variable: { id: "ndvi", name: "NDVI", description: "", annual_value_definition: "annual mean NDVI" },
    dataset: { source: "MODIS", id: "MOD13Q1", version: "061", provenance: "satellite", doi: null },
    spatial_support: { mode: "point", type: "pixel_circle", description: "250 m pixels", resolution: "250 m", requested: { latitude: 16.8661, longitude: 96.1951 } },
    period: { start: "2015-01-01", end_exclusive: "2025-01-01" },
    units: { annual_value: "NDVI", slope: "NDVI/year" },
    annual: years.map((y) => ({ year: y, value: 0.5, eligible: true, reasons: [], complete_calendar_year: true, coverage_percentage: 100, represented_months: null, missing_months: null, extra: {} })),
    series: [],
    series_definition: "monthly mean NDVI",
    trend: {
      result_level: "statistical_inference", result_level_label: "Slope with significance test", eligible_years: years, excluded_years: [], missing_years: [],
      slope: 0.002, intercept: -3.5, slope_units: "NDVI/year", confidence_interval: [-0.001, 0.005], confidence_interval_unavailable_reason: null,
      mann_kendall: { s: 3, tau: 0.07, p_value: 0.72, alpha: 0.05, is_statistically_significant: false, direction: "no_detected_trend" },
      serial_dependence: null, slope_unavailable_reason: null, significance_unavailable_reason: null,
    },
    coverage: { years_requested: 10, eligible_years: 10, excluded_years: [] },
    methodology: { source: {}, trend_method: {} },
    caveats: ["Indicative caveat."],
    limitations: [],
    extra: {},
    data_status: "live_nasa_retrieval",
    ...overrides,
  };
}

describe("calendar-complete monthly series", () => {
  it("inserts explicit null months for omitted months and never fabricates values", () => {
    const rows = calendarSeries(
      [
        { date: "2015-01-01", value: 0.4 },
        { date: "2015-02-01", value: 0.42 },
        { date: "2015-05-01", value: 0.5 },
        { date: "2015-06-01", value: null, usable: false, status: "insufficient_support" },
      ],
      "2015-01-01",
      "2015-08-01",
    );
    expect(rows.map((r) => r.month)).toEqual(["2015-01", "2015-02", "2015-03", "2015-04", "2015-05", "2015-06", "2015-07"]);
    expect(rows.filter((r) => r.value !== null).map((r) => r.value)).toEqual([0.4, 0.42, 0.5]);
    expect(rows[2]).toMatchObject({ value: null, state: "not_returned" });
    expect(rows[5]).toMatchObject({ value: null, state: "withheld", status: "insufficient_support" });
    // May sits between gaps, so it must get a visible dot.
    expect(rows[4]!.isolated).toBe(true);
    expect(rows[0]!.isolated).toBe(false);
    expect(gapRuns(rows)).toEqual([
      { from: "2015-03", to: "2015-04", months: 2 },
      { from: "2015-06", to: "2015-07", months: 2 },
    ]);
  });

  it("keeps observations that fall outside the stated period", () => {
    const rows = calendarSeries([{ date: "2014-12-01", value: 1 }, { date: "2015-01-01", value: 2 }], "2015-01-01", "2015-02-01");
    expect(rows.map((r) => r.month)).toEqual(["2014-12", "2015-01"]);
  });
});

describe("trend verdicts", () => {
  it("never labels a non-significant test as unchanged", () => {
    const v = trendVerdict(base());
    expect(v.label).toBe("No trend detected");
    expect(v.note).toMatch(/not proof of no change/);
  });

  it("says 'Trend unavailable' (not 'No trend') when no slope exists", () => {
    const a = base({ trend: { ...base().trend!, result_level: "annual_summaries_only", slope: null, mann_kendall: null } });
    expect(trendVerdict(a).inference).toBe("Trend unavailable");
    expect(trendVerdict(base({ trend: null })).kind).toBe("unavailable");
  });

  it("marks significant results as indicative and descriptive slopes as descriptive", () => {
    const sig = base({ trend: { ...base().trend!, slope: -0.01, mann_kendall: { ...base().trend!.mann_kendall!, is_statistically_significant: true } } });
    expect(trendVerdict(sig)).toMatchObject({ kind: "decreasing", label: "Indicative decrease", inference: "Significant*" });
    const desc = base({ trend: { ...base().trend!, result_level: "descriptive_slope", mann_kendall: null } });
    expect(trendVerdict(desc).kind).toBe("descriptive");
  });
});

describe("result presentation", () => {
  it("renders the unavailable state without implying no change", () => {
    const a = base({ trend: { ...base().trend!, result_level: "annual_summaries_only", slope: null, intercept: null, mann_kendall: null, confidence_interval: null } });
    render(<ResultSummary analysis={a} place="Yangon" />);
    expect(screen.getByRole("heading", { name: /isn’t enough reliable data/ })).toBeInTheDocument();
    expect(screen.getAllByText("Trend unavailable").length).toBeGreaterThan(0);
    expect(screen.queryByText("No trend")).not.toBeInTheDocument();
    expect(screen.getByText("Yangon")).toBeInTheDocument();
  });

  it("describes whether the confidence interval includes zero", () => {
    render(<CiRuler slope={0.02} ci={[-0.07, 0.1]} units="°C/year" />);
    expect(screen.getByRole("img", { name: /includes zero/ })).toBeInTheDocument();
  });

  it("labels each month cell for screen readers", () => {
    const annual = [{ year: 2020, value: 1, eligible: false, reasons: [], complete_calendar_year: true, coverage_percentage: 90, represented_months: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], missing_months: [12], extra: {} }];
    render(<MonthMatrix annual={annual} />);
    expect(screen.getByText("December 2020: missing")).toBeInTheDocument();
    expect(screen.getByText("11/12")).toBeInTheDocument();
  });
});
