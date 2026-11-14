import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Analysis, VariableInfo } from "./api/types";
import { validateSelection, yearLimits } from "./components/AnalysisControls";
import { buildRows } from "./components/TrendChart";
import { decadeUnits, fmt, reasonLabel, signed } from "./lib/format";
import { stepWarning, summarize } from "./lib/summary";
import { DEFAULT_SELECTION, parseSelection, serializeSelection, toRequest } from "./state/selection";

vi.mock("./components/MapView", () => ({
  default: ({ onSelect }: { onSelect: (lat: number, lon: number) => void }) => (
    <button type="button" onClick={() => onSelect(-1.2864, 36.8172)}>mock map</button>
  ),
}));

const VARIABLE: VariableInfo = {
  id: "temperature", name: "Air temperature (2 m)", short_name: "Temperature", description: "Annual mean temperature.",
  annual_value: "annual mean of 12 monthly means", units: "°C", slope_units: "°C/year",
  dataset: { source: "NASA POWER", id: "T2M", version: "v2", provenance: "reanalysis", doi: null },
  spatial_resolution: "0.5° × 0.625° grid cell", temporal_resolution: "daily", available_from: "1981-01-01",
  max_years: 50, default_period: [2015, 2025], modes: { point: true, region: false }, region_unsupported_reason: "Not implemented.",
};
const NDVI: VariableInfo = { ...VARIABLE, id: "ndvi", short_name: "NDVI", max_years: 10, available_from: "2000-02-18", modes: { point: true, region: true }, region_unsupported_reason: null, max_radius_km: 100 };

function analysis(overrides: Partial<Analysis> = {}): Analysis {
  const years = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024];
  return {
    variable: { id: "temperature", name: "Air temperature (2 m)", description: "", annual_value_definition: "annual mean of 12 monthly means" },
    dataset: { source: "NASA POWER", id: "POWER daily T2M", version: "v2", provenance: "reanalysis-based model estimate", doi: null },
    spatial_support: { mode: "point", type: "grid_cell_estimate", description: "NASA POWER grid-cell estimate", resolution: "0.5° × 0.625° grid cell",
      cell: { center: [17, 96.25], bounds: { south: 16.75, north: 17.25, west: 95.9375, east: 96.5625 }, approximate: true }, requested: { latitude: 16.8661, longitude: 96.1951 } },
    period: { start: "2015-01-01", end_exclusive: "2025-01-01" },
    units: { annual_value: "°C", slope: "°C/year" },
    annual: years.map((y, i) => ({ year: y, value: 27 + i * 0.05, eligible: y !== 2018, reasons: y === 2018 ? ["insufficient_represented_months"] : [],
      complete_calendar_year: true, coverage_percentage: 100, represented_months: [], missing_months: [], extra: {} })),
    series: [{ date: "2015-01-01", value: 24.5 }],
    series_definition: "monthly mean (°C)",
    trend: { result_level: "statistical_inference", result_level_label: "Slope with significance test", eligible_years: years.filter((y) => y !== 2018), excluded_years: [], missing_years: [2018],
      slope: 0.05, intercept: -73.75, slope_units: "°C/year", confidence_interval: [0.01, 0.09], confidence_interval_unavailable_reason: null,
      mann_kendall: { s: 30, tau: 0.8, p_value: 0.003, alpha: 0.05, is_statistically_significant: true, direction: "increasing" },
      serial_dependence: null, slope_unavailable_reason: null, significance_unavailable_reason: null },
    coverage: { years_requested: 10, eligible_years: 9, excluded_years: [{ year: 2018, reasons: ["insufficient_represented_months"] }] },
    methodology: { source: {}, trend_method: { slope: "Theil–Sen" } },
    caveats: ["Mann-Kendall significance is indicative.", "Descriptive slope note."],
    limitations: ["Model estimate, not a station."],
    extra: {},
    data_status: "live_nasa_retrieval",
    cache: { hit: false, retrieved_at: "2026-11-13T10:00:00+00:00", age_seconds: 0 },
    ...overrides,
  };
}

describe("formatting", () => {
  it("formats numbers, signs and units", () => {
    expect(fmt(null)).toBe("—");
    expect(signed(0.0205, 4)).toBe("+0.0205");
    expect(signed(-1.5, 2)).toBe("−1.5");
    expect(decadeUnits("°C/year")).toBe("°C/decade");
    expect(decadeUnits("mm/year²")).toBe("mm/year per decade");
    expect(reasonLabel("partial_calendar_year")).toBe("Partial calendar year");
    expect(reasonLabel("some_new_code")).toBe("Some new code");
  });
});

describe("selection state", () => {
  it("round-trips through the URL and rejects invalid values", () => {
    const s = { ...DEFAULT_SELECTION, latitude: -1.2864, longitude: 36.8172, variable: "ndvi" as const, mode: "region" as const, radiusKm: 12, placeName: "Nairobi" };
    expect(parseSelection(`?${serializeSelection(s)}`)).toEqual(s);
    const bad = parseSelection("?lat=200&lon=-999&v=nope&mode=x");
    expect(bad.latitude).toBe(DEFAULT_SELECTION.latitude);
    expect(bad.variable).toBe("temperature");
    expect(bad.mode).toBe("point");
  });

  it("converts the inclusive end year to an exclusive request bound", () => {
    expect(toRequest({ ...DEFAULT_SELECTION, endYearInclusive: 2024 }).endYear).toBe(2025);
  });
});

describe("validation", () => {
  it("enforces availability, maximum span and region support", () => {
    expect(validateSelection(VARIABLE, DEFAULT_SELECTION)).toBeNull();
    expect(validateSelection(VARIABLE, { ...DEFAULT_SELECTION, startYear: 2024, endYearInclusive: 2015 })).toMatch(/start year/);
    expect(validateSelection(NDVI, { ...DEFAULT_SELECTION, variable: "ndvi", startYear: 2001, endYearInclusive: 2020 })).toMatch(/At most 10/);
    expect(validateSelection(VARIABLE, { ...DEFAULT_SELECTION, mode: "region" })).toBe("Not implemented.");
    expect(validateSelection(NDVI, { ...DEFAULT_SELECTION, variable: "ndvi", startYear: 1995, endYearInclusive: 2000 })).toMatch(/covers 2000/);
  });

  it("limits SMAP V005 to its own record", () => {
    const sm = { ...VARIABLE, id: "soil_moisture" as const, available_from: "2000-01-01" };
    expect(yearLimits(sm, { ...DEFAULT_SELECTION, variable: "soil_moisture", dataset: "smap_l3e_v005_am" })).toMatchObject({ min: 2015, max: 2023 });
  });
});

describe("summary and chart rows", () => {
  it("reports significance cautiously and mentions exclusions", () => {
    const lines = summarize(analysis());
    expect(lines[0]).toMatch(/9 eligible years \(2015–2024\)/);
    expect(lines[1]).toMatch(/indicative/);
    expect(lines.join(" ")).toMatch(/1 year\(s\) were excluded/);
  });

  it("explains when no trend can be estimated", () => {
    const a = analysis({ trend: { ...analysis().trend!, result_level: "annual_summaries_only", slope: null, intercept: null, slope_unavailable_reason: "At least 3 eligible annual observations are required" } });
    expect(summarize(a)[0]).toMatch(/not enough to estimate a trend/);
  });

  it("states that no neighbouring cell was substituted for masked cells", () => {
    const a = analysis({ spatial_support: { ...analysis().spatial_support, cell_status: "no_valid_land_values" } });
    expect(summarize(a)[0]).toMatch(/No neighbouring cell was substituted/);
  });

  it("draws the trend only across eligible years and separates excluded years", () => {
    const rows = buildRows(analysis());
    const r2018 = rows.find((r) => r.year === 2018)!;
    expect(r2018.eligible).toBeNull();
    expect(r2018.excluded).not.toBeNull();
    expect(rows[0]!.trend).toBeCloseTo(-73.75 + 0.05 * 2015);
  });
});

describe("step check", () => {
  it("warns only when a sudden step was detected", () => {
    expect(stepWarning(analysis())).toBeNull();
    const base = analysis();
    const stepped = analysis({ trend: { ...base.trend!, change_point: { status: "step_detected", last_year_before: 2007, first_year_after: 2008, shift: -1.33 } } });
    expect(stepWarning(stepped)).toContain("between 2007 and 2008 (−1.33 °C)");
    const none = analysis({ trend: { ...base.trend!, change_point: { status: "none" } } });
    expect(stepWarning(none)).toBeNull();
  });
});

describe("seasonal NDVI", () => {
  it("describes the monthly method instead of eligible years", () => {
    const base = analysis();
    const ndvi = analysis({
      coverage: { years_requested: 10, eligible_years: 0, excluded_years: [] },
      trend: { ...base.trend!, method: "seasonal_kendall", months_used: [1, 2, 3, 4, 11, 12], sample_count: 60, slope: 0.0063, slope_units: "NDVI units/year" },
    });
    const text = summarize(ndvi).join(" ");
    expect(text).toContain("60 monthly values from Jan, Feb, Mar, Apr, Nov, Dec");
    expect(text).toContain("Seasonal Kendall test");
    expect(text).not.toContain("excluded from the trend");
    expect(text).not.toContain("Mann–Kendall");
  });
});

describe("Explore flow", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes("/api/v2/variables")) return new Response(JSON.stringify({ variables: [VARIABLE, NDVI], caveats: ["c"], api_version: "2" }), { status: 200 });
      if (url.includes("/api/v2/analysis")) return new Response(JSON.stringify(analysis()), { status: 200 });
      return new Response("{}", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  async function renderApp() {
    const { default: App } = await import("./App");
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
  }

  it("runs an investigation end to end and shows the result with provenance", async () => {
    await renderApp();
    const button = await screen.findByRole("button", { name: "Launch investigation" });
    await userEvent.click(button);
    expect(await screen.findByText("Live NASA data retrieval")).toBeInTheDocument();
    expect(screen.getByText("+0.05")).toBeInTheDocument();
    expect(screen.getByText("Significant*")).toBeInTheDocument();
    expect(screen.getByText("Data provenance")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find((c) => String(c[0]).includes("/api/v2/analysis"))!;
    expect(String(call[0])).toContain("start_date=2015-01-01");
    expect(String(call[0])).toContain("end_date=2025-01-01");
  });

  it("selects a location from the map and disables unsupported region mode", async () => {
    await renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "mock map" }));
    await waitFor(() => expect(screen.getByText(/1\.2864° S, 36\.8172° E/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Region" })).toBeDisabled();
  });

  it("shows a clear error for unsupported locations without a retry button", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes("/api/v2/variables")) return new Response(JSON.stringify({ variables: [VARIABLE], caveats: [], api_version: "2" }), { status: 200 });
      return new Response(JSON.stringify({ detail: { reason: "outside_dataset_coverage", message: "GLDAS-2.1 covers 60S-90N" } }), { status: 422 });
    });
    await renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "Launch investigation" }));
    expect(await screen.findByText("Not available at this location")).toBeInTheDocument();
    expect(screen.getByText("GLDAS-2.1 covers 60S-90N")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("labels cached results with their retrieval time", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes("/api/v2/variables")) return new Response(JSON.stringify({ variables: [VARIABLE], caveats: [], api_version: "2" }), { status: 200 });
      return new Response(JSON.stringify(analysis({ data_status: "cached_nasa_retrieval", cache: { hit: true, retrieved_at: "2026-11-13T10:00:00+00:00", age_seconds: 42 } })), { status: 200 });
    });
    await renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "Launch investigation" }));
    expect(await screen.findByText(/Cached result of a NASA retrieval/)).toBeInTheDocument();
  });
});

describe("offline handling", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("falls back to the saved catalog and offers labelled snapshots when the backend is unreachable", async () => {
    const snap = analysis({ data_status: "saved_snapshot" });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.includes("/api/")) return new Response("<html>not found</html>", { status: 404 });
      if (url.endsWith("snapshots/variables.json")) return new Response(JSON.stringify({ variables: [VARIABLE], caveats: [], api_version: "2" }), { status: 200 });
      if (url.endsWith("snapshots/index.json")) return new Response(JSON.stringify({ captured_at: "2026-11-13", note: "saved", entries: [
        { variable: "temperature", latitude: 16.8661, longitude: 96.1951, startYear: 2015, endYear: 2025, mode: "point", file: "t.json" }] }), { status: 200 });
      if (url.endsWith("snapshots/t.json")) return new Response(JSON.stringify(snap), { status: 200 });
      return new Response("", { status: 404 });
    }));
    window.history.replaceState(null, "", "/");
    const { default: App } = await import("./App");
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><App /></QueryClientProvider>);
    expect(await screen.findByText(/Offline mode/)).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Launch investigation" }));
    expect(await screen.findByText("Analysis service not reachable")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show saved snapshot" }));
    expect(await screen.findByText(/Saved snapshot of a live NASA retrieval \(captured 2026-11-13\)/)).toBeInTheDocument();
  });
});

describe("region boxes", () => {
  it("builds a centred, clipped box and sends it only for precipitation region mode", async () => {
    const { selectionBox } = await import("./state/selection");
    const s = { ...DEFAULT_SELECTION, variable: "precipitation" as const, mode: "region" as const, boxSpan: 1 };
    expect(selectionBox(s)).toEqual([95.6951, 16.3661, 96.6951, 17.3661]);
    expect(selectionBox({ ...s, latitude: 89.8, longitude: 179.9 })).toEqual([179.4, 89.3, 180, 90]);
    expect(toRequest(s).bbox).toEqual([95.6951, 16.3661, 96.6951, 17.3661]);
    expect(toRequest({ ...s, mode: "point" }).bbox).toBeUndefined();
    expect(toRequest({ ...s, variable: "ndvi" }).bbox).toBeUndefined();
    expect(parseSelection(`?${serializeSelection(s)}`).boxSpan).toBe(1);
  });
});
