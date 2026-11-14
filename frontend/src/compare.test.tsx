import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Analysis } from "./api/types";
import type { CompareResponse, DatasetInfo, DatasetResult } from "./api/compareTypes";
import { buildOverlayRows } from "./components/compare/OverlayChart";
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
    const tabs = screen.getByRole("tablist");
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
});
