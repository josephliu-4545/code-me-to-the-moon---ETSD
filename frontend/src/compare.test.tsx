import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Analysis } from "./api/types";
import type { CompareResponse, DatasetInfo, DatasetResult } from "./api/compareTypes";
import { buildOverlayRows } from "./components/compare/OverlayChart";
import EvaluationLab from "./components/evaluation/EvaluationLab";
import CompareDatasetsPage, { coverageWarnings, validateCompare } from "./pages/CompareDatasetsPage";
import { DEFAULT_SELECTION } from "./state/selection";

function info(key: string, over: Partial<DatasetInfo> = {}): DatasetInfo {
  return {
    key, variable: "temperature", name: key.toUpperCase(), provider: "NASA", collection_id: `C/${key}`, version: "1",
    measurement: "m", product_type: "reanalysis", native_units: "K", units: "°C", slope_units: "°C/year",
    temporal_resolution: "monthly", spatial_resolution: "0.1°", available_from: "2000-01-01", available_to: null,
    coverage_note: "global", quality_control: "qc", processing: "p", lineage: "l", shared_inputs: [], limitations: ["lim"],
    citation: "cite", doi: null, license: "open", comparable_quantity: "air_temperature_2m", is_primary: key === "a",
    modes: ["point"], max_years: 30, latitude_limits: [-90, 90], supports_region: false, ...over,
  };
}

function analysis(offset: number, slope: number, eligible = true): Analysis {
  const years = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024];
  return {
    variable: { id: "temperature", name: "T", description: "", annual_value_definition: "mean" },
    dataset: { source: "NASA", id: "x", version: "1", provenance: "p", doi: null },
    spatial_support: { mode: "point", type: "native_grid_cell", description: "cell", resolution: "0.1°", requested: { latitude: 0, longitude: 0 } },
    period: { start: "2015-01-01", end_exclusive: "2025-01-01" },
    units: { annual_value: "°C", slope: "°C/year" },
    annual: years.map((y, i) => ({ year: y, value: offset + i * slope, eligible: eligible && y !== 2018, reasons: y === 2018 ? ["insufficient_represented_months"] : [],
      complete_calendar_year: true, coverage_percentage: 100, represented_months: [], missing_months: [], extra: {} })),
    series: [], series_definition: null,
    trend: { result_level: "descriptive_slope", result_level_label: "Descriptive", eligible_years: years.filter((y) => y !== 2018), excluded_years: [], missing_years: [],
      slope, intercept: offset - 2015 * slope, slope_units: "°C/year", confidence_interval: null, confidence_interval_unavailable_reason: "n/a",
      mann_kendall: null, serial_dependence: null, slope_unavailable_reason: null, significance_unavailable_reason: "screen" },
    coverage: { years_requested: 10, eligible_years: 9, excluded_years: [] },
    methodology: { source: {}, trend_method: { slope: "Theil–Sen" } }, caveats: ["c1", "c2"], limitations: ["lim"], extra: {},
    data_status: "live_nasa_retrieval",
  };
}

const CATALOG = {
  variables: [
    { variable: "temperature", datasets: [info("a"), info("b"), info("c", { latitude_limits: [-50, 50], available_from: "2016-01-01" })],
      comparison_available: true, not_yet_available_reason: null,
      relationships: [{ datasets: ["a", "b"], lineage: "partially_related", note: "share inputs", numerically_comparable: true }] },
    { variable: "ndvi", datasets: [], comparison_available: false, not_yet_available_reason: "NDVI alternatives are planned.", relationships: [] },
  ],
  outcomes: {},
};

function compareResponse(over: Partial<CompareResponse> = {}): CompareResponse {
  const ok = (k: string, a: Analysis): DatasetResult => ({ entry: info(k), outcome: "descriptive_only", message: "Descriptive trend only", analysis: a });
  return {
    variable: "temperature", location: { latitude: 16.8661, longitude: 96.1951, mode: "point" },
    period: { start: "2015-01-01", end_exclusive: "2025-01-01" }, datasets_requested: ["a", "b", "c"], datasets_are_merged: false,
    results: {
      a: ok("a", analysis(27, 0.02)),
      b: ok("b", analysis(28, -0.05)),
      c: { entry: info("c"), outcome: "unsupported_location", message: "C covers latitudes -50° to 50° only", analysis: null },
    },
    succeeded: ["a", "b"],
    comparison: {
      pairs: [{ datasets: ["a", "b"], lineage: "partially_related", lineage_note: "Share inputs.", numerically_comparable: true,
        common_eligible_years: [2015, 2016, 2017, 2019, 2020, 2021, 2022, 2023, 2024], full_period_slopes: { a: 0.02, b: -0.05 },
        common_period_slopes: { a: 0.02, b: -0.05 }, slope_sign_agreement: false, confidence_intervals_overlap: null,
        annual_differences: [], mean_difference: -1.0, mean_absolute_difference: 1.0, difference_units: "°C", difference_label: "not an error",
        spearman_rho: 0.31, pearson_r: 0.3, spearman_rho_year_to_year: 0.63, unavailable_reasons: [] }],
      all_numerically_comparable: true, common_eligible_years_all: [2015, 2016],
      agreement: { level: "conflicting_trend_direction", slope_sign_agreement_all: false, min_spearman_rho: 0.31, explanation: "The datasets disagree on the direction of the trend.", caution: "Agreement does not prove accuracy." },
      method: {},
    },
    comparison_unavailable_reason: null,
    caveats: ["Datasets are never merged."],
    ...over,
  };
}

function evaluationResponse(): CompareResponse {
  const response = compareResponse();
  (response as CompareResponse & { evaluation: unknown }).evaluation = {
    datasets: {
      a: {
        dataset: "a", resolution: "annual", resolution_note: "Annual coverage: monthly quality-control information is not available for this dataset response.",
        requested_period: { start: "2015-01-01", end_exclusive: "2018-01-01" }, supported_period: { start: "2000-01-01", end: null },
        cells: [
          { period: "2015", status: "valid", reasons: [], value: 27 },
          { period: "2016", status: "excluded", reasons: ["insufficient_represented_months"], value: 28 },
          { period: "2017", status: "missing", reasons: ["no_valid_observations"], value: null },
        ],
        counts: { valid: 1, missing: 1, excluded: 1, provisional: 0, outside_coverage: 0, unavailable: 0 },
        completeness: { valid: 1, expected_within_supported_coverage: 3, percentage: 100 / 3, label: "Valid years / Expected years within supported dataset coverage" },
        eligible_years: [2015], excluded_years: [{ year: 2016, reasons: ["insufficient_represented_months"] }],
      },
      b: {
        dataset: "b", resolution: "monthly", resolution_note: "Monthly coverage from genuine monthly observation and quality-control records.",
        requested_period: { start: "2015-01-01", end_exclusive: "2015-04-01" }, supported_period: { start: "2000-01-01", end: null },
        cells: [
          { period: "2015-01", status: "valid", reasons: [], value: 28 },
          { period: "2015-02", status: "provisional", reasons: ["provisional_recent_product"], value: 29 },
          { period: "2015-03", status: "outside_coverage", reasons: ["outside_dataset_record"], value: null },
        ],
        counts: { valid: 1, missing: 0, excluded: 0, provisional: 1, outside_coverage: 1, unavailable: 0 },
        completeness: { valid: 1, expected_within_supported_coverage: 2, percentage: 50, label: "Valid months / Expected months within supported dataset coverage" },
        eligible_years: [2015], excluded_years: [],
      },
      c: {
        dataset: "c", resolution: "annual", resolution_note: "Annual coverage: monthly quality-control information is not available for this dataset response.",
        requested_period: { start: "2015-01-01", end_exclusive: "2018-01-01" }, supported_period: { start: "2016-01-01", end: null },
        cells: [{ period: "2015", status: "outside_coverage", reasons: ["outside_dataset_record"], value: null }, { period: "2016", status: "unavailable", reasons: ["dataset_result_unavailable"], value: null }],
        counts: { valid: 0, missing: 0, excluded: 0, provisional: 0, outside_coverage: 1, unavailable: 1 },
        completeness: { valid: 0, expected_within_supported_coverage: 1, percentage: null, status: "unavailable", unavailable_reason: "Unsupported location; completeness was not assessed.", label: "Completeness unavailable" },
        eligible_years: [], excluded_years: [],
      },
    },
    pairs: [{
      ...response.comparison!.pairs[0]!, root_mean_square_difference: 1.2, slope_difference: 0.07,
      matched_observations: { resolution: "annual", count: 2, period: { start: "2015", end: "2016" }, labels: ["2015", "2016"], valid_observations: { a: ["2015", "2016"], b: ["2015", "2016", "2017"] }, excluded_from_pairing: { a: [], b: ["2017"] }, quality_excluded: { a: ["2018"], b: [] } },
      annual_differences: [{ year: 2015, difference: -1 }, { year: 2016, difference: -1.4 }],
      metrics: [
        { id: "rmse", name: "Root mean square difference", value: 1.2, units: "°C", matched_observations: 2, definition: "Square root of mean squared product differences.", interpretation: "A product-to-product difference, not an error.", limitations: "Neither product is ground truth.", availability: "available", unavailable_reason: null },
        { id: "pearson_r", name: "Pearson correlation", value: null, units: null, matched_observations: 2, definition: "Linear correlation.", interpretation: "Co-variation, not causation.", limitations: "No p-value.", availability: "unavailable", unavailable_reason: "Requires at least 8 common eligible years." },
      ],
    }],
    cautions: ["Agreement between products does not establish accuracy, measurement truth, or causation."],
  };
  return response;
}

describe("comparison helpers", () => {
  it("keeps eligible values, excluded values and each dataset's own trend separate", () => {
    const results: DatasetResult[] = [
      { entry: info("a"), outcome: "descriptive_only", message: "", analysis: analysis(27, 0.02) },
      { entry: info("b"), outcome: "descriptive_only", message: "", analysis: analysis(28, -0.05) },
    ];
    const rows = buildOverlayRows(results);
    const r2018 = rows.find((r) => r.year === 2018)!;
    expect(r2018.a).toBeNull();
    expect(r2018.a__excluded).toBeCloseTo(27 + 3 * 0.02);
    expect(rows[0]!.b__trend).toBeCloseTo(28);
    expect(rows[0]!.a).toBeCloseTo(27);
  });

  it("validates selection size and per-dataset request limits", () => {
    const ds = [info("a"), info("b", { max_years: 10 })];
    expect(validateCompare(["a"], ds, 2015, 2024)).toMatch(/at least two/);
    expect(validateCompare(["a", "b"], ds, 2015, 2024)).toBeNull();
    expect(validateCompare(["a", "b"], ds, 2001, 2024)).toMatch(/at most 10 years/);
    expect(validateCompare(["a", "b", "c", "d", "e"], [...ds, info("c"), info("d"), info("e")], 2015, 2024)).toMatch(/at most four/);
  });

  it("warns about coverage and record limits before running", () => {
    const w = coverageWarnings([info("c", { latitude_limits: [-50, 50], available_from: "2016-01-01", available_to: "2023-12-02" })], 2015, 2024, 60);
    expect(w.join(" ")).toMatch(/does not cover latitude 60/);
    expect(w.join(" ")).toMatch(/starts in 2016/);
    expect(w.join(" ")).toMatch(/ends on 2023-12-02/);
  });
});

describe("Compare datasets page", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  function renderPage(response: CompareResponse) {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes("/api/v2/datasets")) return new Response(JSON.stringify(CATALOG), { status: 200 });
      if (url.includes("/api/v2/compare")) return new Response(JSON.stringify(response), { status: 200 });
      return new Response("{}", { status: 404 });
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(<QueryClientProvider client={client}><CompareDatasetsPage selection={DEFAULT_SELECTION} /></QueryClientProvider>);
  }

  it("runs a comparison with partial failure and switches to an individual dataset", async () => {
    renderPage(compareResponse());
    expect(await screen.findByText("Vegetation (NDVI): NDVI alternatives are planned.")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Vegetation/ })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Compare datasets" }));
    expect(await screen.findByText(/Agreement: Conflicting trend direction/)).toBeInTheDocument();
    const call = fetchMock.mock.calls.find((c) => String(c[0]).includes("/api/v2/compare"))!;
    expect(String(call[0])).toContain("datasets=a%2Cb%2Cc");
    expect(String(call[0])).toContain("end_date=2025-01-01");
    expect(screen.getByLabelText(/C: C covers latitudes/)).toBeInTheDocument();
    expect(screen.getByText("Pairwise comparison")).toBeInTheDocument();
    const tabs = screen.getByRole("tablist", { name: "Comparison dataset view" });
    expect(within(tabs).queryByRole("tab", { name: "C" })).not.toBeInTheDocument();
    await userEvent.click(within(tabs).getByRole("tab", { name: "B" }));
    expect(screen.getByText("Data provenance")).toBeInTheDocument();
  });

  it("requires at least two datasets", async () => {
    renderPage(compareResponse());
    await screen.findByText("2 · Datasets (choose 2–4)");
    await userEvent.click(screen.getByRole("checkbox", { name: /^B/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /^C/ }));
    expect(screen.getByText("Select at least two datasets.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Compare datasets" })).toBeDisabled();
  });

  it("does not present submitted comparison results as current after dataset controls change", async () => {
    renderPage(compareResponse());
    await userEvent.click(await screen.findByRole("button", { name: "Compare datasets" }));
    expect(await screen.findByText(/Agreement: Conflicting trend direction/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("checkbox", { name: /^C/ }));

    expect(screen.queryByText(/Agreement: Conflicting trend direction/)).not.toBeInTheDocument();
  });

  it("allows a replacement comparison while the obsolete request is still fetching", async () => {
    let resolveFirst!: (value: Response) => void;
    let firstSignal: AbortSignal | undefined;
    let compareCalls = 0;
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/api/v2/datasets")) return Promise.resolve(new Response(JSON.stringify(CATALOG), { status: 200 }));
      if (url.includes("/api/v2/compare")) {
        compareCalls += 1;
        if (compareCalls === 1) {
          firstSignal = init?.signal ?? undefined;
          return new Promise<Response>((resolve) => { resolveFirst = resolve; });
        }
        const current = compareResponse({ datasets_requested: ["a", "b"] });
        current.comparison!.agreement.explanation = "Current replacement response.";
        return Promise.resolve(new Response(JSON.stringify(current), { status: 200 }));
      }
      return Promise.resolve(new Response("{}", { status: 404 }));
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><CompareDatasetsPage selection={DEFAULT_SELECTION} /></QueryClientProvider>);

    await userEvent.click(await screen.findByRole("button", { name: "Compare datasets" }));
    await userEvent.click(screen.getByRole("checkbox", { name: /^C/ }));

    const replacement = screen.getByRole("button", { name: "Compare datasets" });
    expect(replacement).toBeEnabled();
    await userEvent.click(replacement);
    expect(firstSignal?.aborted).toBe(true);
    expect(await screen.findByText("Current replacement response.")).toBeInTheDocument();

    const obsolete = compareResponse();
    obsolete.comparison!.agreement.explanation = "Obsolete response.";
    resolveFirst(new Response(JSON.stringify(obsolete), { status: 200 }));
    await waitFor(() => expect(screen.queryByText("Obsolete response.")).not.toBeInTheDocument());
    expect(screen.getByText("Current replacement response.")).toBeInTheDocument();
  });

  it("explains when no comparison is possible and shows separate charts for different quantities", async () => {
    const resp = compareResponse({ comparison: null, comparison_unavailable_reason: "fewer than two datasets returned results" });
    renderPage(resp);
    await userEvent.click(await screen.findByRole("button", { name: "Compare datasets" }));
    expect(await screen.findByText(/fewer than two datasets returned results/)).toBeInTheDocument();
    expect(screen.getByText(/each is shown on its own axis/)).toBeInTheDocument();
  });

  it("adds Comparison and Evaluation Lab result views without replacing comparison details", async () => {
    renderPage(evaluationResponse());
    await userEvent.click(await screen.findByRole("button", { name: "Compare datasets" }));

    const resultViews = await screen.findByRole("tablist", { name: "Result view" });
    expect(within(resultViews).getByRole("tab", { name: "Comparison" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Trend summary")).toBeInTheDocument();

    await userEvent.click(within(resultViews).getByRole("tab", { name: "Evaluation Lab" }));
    expect(await screen.findByText("Coverage and quality control")).toBeInTheDocument();
    expect(screen.queryByText("Trend summary")).not.toBeInTheDocument();

    await userEvent.click(within(resultViews).getByRole("tab", { name: "Comparison" }));
    expect(screen.getByText("Trend summary")).toBeInTheDocument();
    expect(screen.getByRole("tablist", { name: "Comparison dataset view" })).toBeInTheDocument();
  });

  it("resets to Comparison for a replacement request and does not retain stale lab evidence", async () => {
    renderPage(evaluationResponse());
    await userEvent.click(await screen.findByRole("button", { name: "Compare datasets" }));
    await userEvent.click(await screen.findByRole("tab", { name: "Evaluation Lab" }));
    expect(screen.getByText("Coverage and quality control")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("checkbox", { name: /^C/ }));
    expect(screen.queryByText("Coverage and quality control")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Compare datasets" }));

    expect(await screen.findByText("Trend summary")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Comparison" })).toHaveAttribute("aria-selected", "true");
  });
});

describe("Dataset Evaluation Lab", () => {
  it("renders genuine monthly and explicitly annual coverage with non-color status details", async () => {
    render(<EvaluationLab data={evaluationResponse()} />);

    expect(screen.getByRole("heading", { name: "Annual coverage" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Monthly coverage" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /A, 2016: Excluded by quality control.*too few months with valid data/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /B, 2015-02: Provisional or incomplete/i })).toBeInTheDocument();
    expect(screen.getByText("1 / 3 valid years")).toBeInTheDocument();
    expect(screen.getByText("1 / 2 valid months")).toBeInTheDocument();
    expect(screen.getAllByText(/within supported dataset coverage/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Completeness unavailable")).toHaveLength(2);
    expect(screen.getByText("Unsupported location; completeness was not assessed.")).toBeInTheDocument();
  });

  it("shows matched evidence, metric definitions, unavailable reasons, and product differences", () => {
    render(<EvaluationLab data={evaluationResponse()} />);

    expect(screen.getByText("2 matched annual observations")).toBeInTheDocument();
    expect(screen.getByText("Root mean square difference")).toBeInTheDocument();
    expect(screen.getByText("1.200 °C")).toBeInTheDocument();
    expect(screen.getByText("Requires at least 8 common eligible years.")).toBeInTheDocument();
    expect(screen.getAllByText(/A minus B/).length).toBeGreaterThan(0);
    expect(screen.getByRole("table", { name: "Matched product differences" })).toHaveTextContent("2015");
    expect(screen.getByText(/does not establish accuracy/)).toBeInTheDocument();
  });
});
