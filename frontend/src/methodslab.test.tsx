import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MethodsLab as Lab } from "./api/methodsLabTypes";
import type { Analysis, AnalysisRequest } from "./api/types";
import { buildComparisonRows } from "./components/methodslab/MethodComparisonChart";
import MethodsLab from "./components/methodslab/MethodsLab";
import { SIM_BASE, SIM_STEPS, simulate } from "./components/methodslab/OutlierExperiment";
import { ols, theilSen } from "./lib/robustStats";
import EvaluationPage from "./pages/EvaluationPage";

// Reference values from NumPy polyfit and SciPy theilslopes(method="separate") on the same simulated data.
const REF = {
  clean: { ols: [0.4972027972, 10.0181818182], ts: [0.4944444444, 9.9861111111] },
  plus8at12: { ols: [0.8048951049, 8.6848484848], ts: [0.5171428571, 9.8385714286] },
  minus6at3: { ols: [0.6440559441, 8.5636363636], ts: [0.5183333333, 9.8308333333] },
};

function annualLab(over: Partial<Lab> = {}): Lab {
  return {
    applicable: { annual_comparison: true, seasonal: false },
    requirements: { minimum_years_for_slope: 3, minimum_years_for_significance: 8, alpha: 0.05, dependence_screen: "lag-1 Spearman ρ ≥ 0.3 or p < 0.05 withholds significance" },
    mann_kendall: { s: 21, tau: 0.47, p_value: 0.074, alpha: 0.05, is_statistically_significant: false, direction: "no_detected_trend", z: 1.79 },
    significance_unavailable_reason: null,
    serial_dependence: { adjacent_pair_count: 8, lag1_spearman_rho: 0.12, diagnostic_p_value: 0.74, status: "not_detected_with_caveat", caveat: "c", supported_for_standard_inference: true, unavailable_reason: null },
    change_point: { status: "none", pettitt_p_value: 0.4, mean_before: 27.5, mean_after: 27.8, step_fits_better_than_line: false, last_year_before: 2018, first_year_after: 2019 },
    methods: { ols: { name: "Ordinary least squares (descriptive)", definition: "d", role: "Descriptive comparison only." }, theil_sen: { name: "Theil–Sen estimator", definition: "d", role: "r" }, seasonal_kendall: { name: "Seasonal Kendall", definition: "d", role: "r" } },
    observations: { basis: "eligible annual values", eligible: [2015, 2016, 2018, 2019].map((y, i) => ({ year: y, value: 27 + 0.1 * i })), excluded: [{ year: 2017, value: 30, reasons: ["insufficient_represented_months"] }] },
    ols: { available: true, n: 4, slope: 0.025, intercept: -23.4, r_squared: 0.97, r_squared_unavailable_reason: null, residuals: [], unavailable_reason: null, slope_units: "°C/year", inference: null, inference_note: "No p-value or confidence interval is reported for OLS." },
    theil_sen: { available: true, n: 4, slope: 0.02, intercept: -13.3, slope_units: "°C/year", confidence_interval: null, confidence_interval_unavailable_reason: "Inferential confidence interval not supported", unavailable_reason: null, source: "existing" },
    comparison: { same_observations: true, n: 4, slope_difference: 0.005, slope_units: "°C/year", fit_range: [2015, 2019], note: "n",
      fitted: [2015, 2016, 2018, 2019].map((y, i) => ({ year: y, observed: 27 + 0.1 * i, ols: -23.4 + 0.025 * y, theil_sen: -13.3 + 0.02 * y })) },
    seasonal: null,
    seasonal_unavailable_reason: "Seasonal methods apply to the NDVI analysis.",
    ...over,
  };
}

function seasonalLab(): Lab {
  return {
    ...annualLab(),
    applicable: { annual_comparison: false, seasonal: true },
    annual_comparison_unavailable_reason: "This variable's trend uses the Seasonal Kendall method on monthly values, so an annual OLS vs Theil–Sen comparison would use a different sample.",
    serial_dependence: null, ols: undefined, theil_sen: undefined, comparison: undefined,
    observations: { basis: "monthly means in the months used by the seasonal method", eligible: [], excluded: [] },
    seasonal: { method: "seasonal_kendall", months_used: [1, 2, 3, 11, 12], months_not_used: [4, 5, 6, 7, 8, 9, 10], month_names_used: ["Jan", "Feb", "Mar", "Nov", "Dec"],
      years_contributing: [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024], sample_count: 46, seasonal_sen_slope: 0.0042, slope_units: "NDVI units/year",
      confidence_interval: [0.001, 0.007], confidence_interval_unavailable_reason: null,
      seasonal_kendall: { s: 120, tau: 0.21, p_value: 0.003, alpha: 0.05, is_statistically_significant: true, direction: "increasing", z: 2.9 },
      deseasonalized_ols_slope: 0.0039, deseasonalized_ols_unavailable_reason: null, comparison_note: "They are related but not identical estimators.", availability_rule: "A calendar month is used only if it has data in at least 70% of the years." },
  };
}

function analysis(lab: Lab | undefined, name = "Air temperature (2 m)"): Analysis {
  return {
    variable: { id: "temperature", name, description: "", annual_value_definition: "mean" },
    dataset: { source: "NASA POWER", id: "T2M", version: "v2", provenance: "reanalysis", doi: null },
    spatial_support: { mode: "point", type: "grid_cell_estimate", description: "cell", resolution: "0.5°", requested: { latitude: 16.8661, longitude: 96.1951 } },
    period: { start: "2015-01-01", end_exclusive: "2025-01-01" }, units: { annual_value: "°C", slope: "°C/year" },
    annual: [], series: [], series_definition: null, trend: null,
    coverage: { years_requested: 5, eligible_years: 4, excluded_years: [] },
    methodology: { source: {}, trend_method: { slope: "Theil–Sen" } }, caveats: ["c1", "c2"], limitations: [], extra: {},
    methods_lab: lab, data_status: "live_nasa_retrieval",
  } as Analysis;
}

describe("simulation statistics (browser, simulation only)", () => {
  it("match NumPy and SciPy reference values", () => {
    const close = (a: number, b: number) => expect(a).toBeCloseTo(b, 8);
    const c = simulate(12, 0);
    close(c.ols.slope, REF.clean.ols[0]!); close(c.ols.intercept, REF.clean.ols[1]!);
    close(c.theilSen.slope, REF.clean.ts[0]!); close(c.theilSen.intercept, REF.clean.ts[1]!);
    const p = simulate(12, 8);
    close(p.ols.slope, REF.plus8at12.ols[0]!); close(p.theilSen.slope, REF.plus8at12.ts[0]!); close(p.theilSen.intercept, REF.plus8at12.ts[1]!);
    const m = simulate(3, -6);
    close(m.ols.slope, REF.minus6at3.ols[0]!); close(m.ols.intercept, REF.minus6at3.ols[1]!); close(m.theilSen.slope, REF.minus6at3.ts[0]!);
  });

  it("returns null for degenerate input and never mutates the base data", () => {
    expect(ols([1], [2])).toBeNull();
    expect(theilSen([1, 1], [2, 3])).toBeNull();
    const before = [...SIM_BASE];
    simulate(5, 9);
    expect(SIM_BASE).toEqual(before);
    expect(SIM_STEPS).toHaveLength(12);
  });
});

describe("Statistical Methods Lab", () => {
  it("shows observations used, exclusions with reasons, and applicable methods", () => {
    render(<MethodsLab analysis={analysis(annualLab())} />);
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("2015, 2016, 2018, 2019")).toBeInTheDocument();
    expect(screen.getByText("Too few months with valid data")).toBeInTheDocument();
    expect(screen.getByText("Ordinary least squares (descriptive)")).toBeInTheDocument();
    expect(screen.queryByText("Seasonal Kendall")).not.toBeInTheDocument();
  });

  it("compares OLS and Theil–Sen on the same eligible years without OLS significance", async () => {
    render(<MethodsLab analysis={analysis(annualLab())} />);
    await userEvent.click(screen.getByRole("tab", { name: "OLS vs Theil–Sen" }));
    const table = screen.getByTestId("estimator-table");
    expect(within(table).getByText("Theil–Sen (the trend reported)")).toBeInTheDocument();
    expect(within(table).getByText("OLS (descriptive only)")).toBeInTheDocument();
    expect(within(table).getByText("Inferential confidence interval not supported")).toBeInTheDocument();
    expect(screen.getByTestId("slope-difference")).toHaveTextContent("+0.005 °C/year on the same 4 eligible years");
    expect(screen.getByText(/No p-value or confidence interval is reported for OLS/)).toBeInTheDocument();
    expect(screen.queryByText(/OLS.*significant/i)).not.toBeInTheDocument();
  });

  it("keeps excluded years out of the fitted lines", () => {
    const rows = buildComparisonRows(annualLab());
    const r2017 = rows.find((r) => r.year === 2017)!;
    expect(r2017.excluded).toBe(30);
    expect(r2017.ols).toBeNull();
    expect(r2017.theil_sen).toBeNull();
    expect(rows.filter((r) => r.ols !== null).map((r) => r.year)).toEqual([2015, 2016, 2018, 2019]);
  });

  it("supports keyboard navigation between method tabs", async () => {
    render(<MethodsLab analysis={analysis(annualLab())} />);
    const overview = screen.getByRole("tab", { name: "Overview" });
    overview.focus();
    fireEvent.keyDown(overview, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "OLS vs Theil–Sen" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "OLS vs Theil–Sen" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("tab", { name: "OLS vs Theil–Sen" }), { key: "End" });
    expect(screen.getByRole("tab", { name: "Assumptions" })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Assumptions" }), { key: "Home" });
    expect(overview).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(overview, { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: "Assumptions" })).toHaveAttribute("aria-selected", "true");
  });

  it("explains significance correctly and shows unavailable reasons", async () => {
    const { unmount } = render(<MethodsLab analysis={analysis(annualLab())} />);
    await userEvent.click(screen.getByRole("tab", { name: "Trend significance" }));
    expect(screen.getByTestId("mk-results")).toHaveTextContent("21");
    expect(screen.getByText(/It is not the probability that there is no trend/)).toBeInTheDocument();
    expect(screen.getByText(/It does not show what caused it/)).toBeInTheDocument();
    unmount();
    render(<MethodsLab analysis={analysis(annualLab({ mann_kendall: null, significance_unavailable_reason: "At least 8 eligible annual observations are required" }))} />);
    await userEvent.click(screen.getByRole("tab", { name: "Trend significance" }));
    expect(screen.getByText("At least 8 eligible annual observations are required")).toBeInTheDocument();
  });

  it("shows autocorrelation diagnostics with the independence caveat", async () => {
    render(<MethodsLab analysis={analysis(annualLab())} />);
    await userEvent.click(screen.getByRole("tab", { name: "Autocorrelation" }));
    expect(screen.getByTestId("dependence-results")).toHaveTextContent("0.12");
    expect(screen.getByText(/does not prove the years are independent/)).toBeInTheDocument();
  });

  it("uses the seasonal panel for NDVI and refuses an annual comparison on a different sample", async () => {
    render(<MethodsLab analysis={analysis(seasonalLab(), "Vegetation (NDVI)")} />);
    await userEvent.click(screen.getByRole("tab", { name: "Seasonal estimators" }));
    expect(screen.getByText(/would use a different sample/)).toBeInTheDocument();
    expect(screen.getByText("Seasonal Sen slope (the trend reported)")).toBeInTheDocument();
    expect(screen.getByText(/not identical estimators/)).toBeInTheDocument();
    expect(screen.getByText(/Months not used: 4, 5, 6, 7, 8, 9, 10/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Autocorrelation" }));
    expect(screen.getByText(/does not run the lag-1 annual residual screen/)).toBeInTheDocument();
  });

  it("explains when the lab data are missing", () => {
    render(<MethodsLab analysis={analysis(undefined)} />);
    expect(screen.getByText(/does not include Statistical Methods Lab data/)).toBeInTheDocument();
  });

  it("labels the outlier experiment as a simulation and leaves the investigation untouched", async () => {
    const a = analysis(annualLab());
    const snapshot = JSON.stringify(a);
    render(<MethodsLab analysis={a} />);
    await userEvent.click(screen.getByRole("tab", { name: "Outlier experiment" }));
    const sim = screen.getByTestId("outlier-simulation");
    expect(within(sim).getByText(/Not NASA data, not saved/)).toBeInTheDocument();
    expect(within(sim).getByTestId("sim-ols")).toHaveTextContent("0.728");
    fireEvent.change(within(sim).getByLabelText(/Outlier size/), { target: { value: "8" } });
    expect(within(sim).getByTestId("sim-ols")).toHaveTextContent("0.8049");
    expect(within(sim).getByTestId("sim-ts")).toHaveTextContent("0.5171");
    expect(JSON.stringify(a)).toBe(snapshot);
  });
});

describe("Scientific Evaluation integration", () => {
  afterEach(() => vi.unstubAllGlobals());

  function renderPage(submitted: AnalysisRequest, responses: Record<string, unknown>, status = 200) {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const name = new URL(url, "http://x").searchParams.get("variable") ?? "";
      return new Response(JSON.stringify(responses[name] ?? { detail: "boom" }), { status: responses[name] ? status : 502 });
    }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const ui = (s: AnalysisRequest) => <QueryClientProvider client={client}><EvaluationPage submitted={s} /></QueryClientProvider>;
    const r = render(ui(submitted));
    return { ...r, rerenderWith: (s: AnalysisRequest) => r.rerender(ui(s)) };
  }

  const req = (variable: AnalysisRequest["variable"]): AnalysisRequest => ({ variable, latitude: 16.8661, longitude: 96.1951, startYear: 2015, endYear: 2025, mode: "point" });

  it("switches between Scientific Evaluation and the lab, and follows the newest analysis", async () => {
    const t = { ...analysis(annualLab()), annual: [{ year: 2015, value: 27, eligible: true, reasons: [], complete_calendar_year: true, coverage_percentage: 100, represented_months: [], missing_months: [], extra: {} }] };
    const n = { ...analysis(seasonalLab(), "Vegetation (NDVI)"), variable: { id: "ndvi", name: "Vegetation (NDVI)", description: "", annual_value_definition: "m" } };
    const { rerenderWith } = renderPage(req("temperature"), { temperature: t, ndvi: n });
    await userEvent.click(await screen.findByRole("button", { name: "Statistical Methods Lab" }));
    expect(screen.getByRole("tab", { name: "OLS vs Theil–Sen" })).toBeInTheDocument();
    rerenderWith(req("ndvi"));
    expect(await screen.findByRole("tab", { name: "Seasonal estimators" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "OLS vs Theil–Sen" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Scientific Evaluation" }));
    expect(screen.queryByRole("tablist", { name: "Statistical methods" })).not.toBeInTheDocument();
  });

  it("shows loading and error states before the lab", async () => {
    renderPage(req("precipitation"), {});
    expect(screen.getByText("Waiting for the analysis…")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Statistical Methods Lab" })).not.toBeInTheDocument();
  });
});

describe("estimator reading", () => {
  it("reports the slope difference descriptively without claiming agreement or attributing causes", async () => {
    const { ESTIMATOR_READING } = await import("./components/methodslab/MethodsLab");
    expect(ESTIMATOR_READING).toMatch(/No formal test of agreement between the estimators was performed/);
    expect(ESTIMATOR_READING).toMatch(/not in the difference between the two estimators/);
    expect(ESTIMATOR_READING).not.toMatch(/consistent|agree(?!ment)|outlier|ends of the record|likely/i);
  });

  it("shows that reading under the slope difference, whatever the interval", () => {
    render(<MethodsLab analysis={analysis(annualLab())} />);
    fireEvent.click(screen.getByRole("tab", { name: "OLS vs Theil–Sen" }));
    const diff = screen.getByTestId("slope-difference");
    expect(diff).toHaveTextContent("No formal test of agreement");
    expect(diff).not.toHaveTextContent(/consistent|outlier/i);
  });
});
