import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Analysis, VariableInfo } from "./api/types";
import LaunchCraft from "./components/explore/LaunchCraft";
import { discoveryHeadline, fittedChange, intervalReading } from "./lib/verdict";
import { launchReducer, PHASE_MS, INITIAL_LAUNCH, useLaunchSequence } from "./state/launch";
import { initialTheme, THEME_KEY } from "./state/theme";

vi.mock("./components/MapView", () => ({ default: () => <div>mock map</div> }));

function mockMatchMedia(matches: Record<string, boolean>) {
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: !!matches[q], media: q, addEventListener: () => {}, removeEventListener: () => {} }));
}

const VARIABLE: VariableInfo = {
  id: "temperature", name: "Air temperature (2 m)", short_name: "Temperature", description: "Annual mean temperature.",
  annual_value: "annual mean", units: "°C", slope_units: "°C/year",
  dataset: { source: "NASA POWER", id: "T2M", version: "v2", provenance: "reanalysis", doi: null },
  spatial_resolution: "0.5° grid", temporal_resolution: "daily", available_from: "1981-01-01",
  max_years: 50, default_period: [2015, 2025], modes: { point: true, region: false }, region_unsupported_reason: "Not implemented.",
};
const NDVI: VariableInfo = { ...VARIABLE, id: "ndvi", name: "Vegetation greenness (NDVI)", short_name: "NDVI", available_from: "2000-02-18", max_years: 10 };

function analysis(overrides: Partial<Analysis> = {}): Analysis {
  const years = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024];
  return {
    variable: { id: "temperature", name: "Air temperature (2 m)", description: "", annual_value_definition: "annual mean" },
    dataset: { source: "NASA POWER", id: "T2M", version: "v2", provenance: "reanalysis-based model estimate", doi: null },
    spatial_support: { mode: "point", type: "grid_cell_estimate", description: "NASA POWER grid-cell estimate", resolution: "0.5° × 0.625° grid cell", requested: { latitude: 16.8661, longitude: 96.1951 } },
    period: { start: "2015-01-01", end_exclusive: "2025-01-01" },
    units: { annual_value: "°C", slope: "°C/year" },
    annual: years.map((y) => ({ year: y, value: 27, eligible: true, reasons: [], complete_calendar_year: true, coverage_percentage: 100, represented_months: null, missing_months: null, extra: {} })),
    series: [],
    series_definition: null,
    trend: {
      result_level: "statistical_inference", result_level_label: "Slope with significance test", eligible_years: years, excluded_years: [], missing_years: [],
      slope: 0.02, intercept: -13, slope_units: "°C/year", confidence_interval: [-0.07, 0.1], confidence_interval_unavailable_reason: null,
      mann_kendall: { s: 1, tau: 0.02, p_value: 1, alpha: 0.05, is_statistically_significant: false, direction: "no_detected_trend" },
      serial_dependence: null, slope_unavailable_reason: null, significance_unavailable_reason: null,
    },
    coverage: { years_requested: 10, eligible_years: 10, excluded_years: [] },
    methodology: { source: {}, trend_method: {} },
    caveats: ["Indicative caveat.", "Not a cause."],
    limitations: [],
    extra: {},
    data_status: "live_nasa_retrieval",
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("theme system", () => {
  it("follows the system preference on first visit and a saved choice afterwards", () => {
    mockMatchMedia({ "(prefers-color-scheme: light)": true });
    expect(initialTheme()).toBe("light");
    window.localStorage.setItem(THEME_KEY, "dark");
    expect(initialTheme()).toBe("dark");
  });

  it("defaults to Orbit (dark) without a preference", () => {
    mockMatchMedia({});
    expect(initialTheme()).toBe("dark");
  });
});

describe("launch sequence", () => {
  const begin = () => launchReducer(INITIAL_LAUNCH,{type:"launch",key:"a"});
  it("progresses through ignition, liftoff and transit into a stable holding state", () => {
    let state = begin(); expect(state.phase).toBe("ignition");
    for (const phase of ["liftoff","transit","holding"]) {
      state = launchReducer(state,{type:"advance",run:1}); expect(state.phase).toBe(phase);
    }
    expect(launchReducer(state,{type:"advance",run:1})).toEqual(state);
  });
  it("docks immediately for fast success without waiting for liftoff", () => {
    const state = launchReducer(begin(),{type:"settled",key:"a",run:1,ok:true});
    expect(state.phase).toBe("docking");
    expect(launchReducer(state,{type:"advance",run:1}).phase).toBe("completed");
  });
  it("fails and cancels immediately, ignoring subsequent settlements", () => {
    expect(launchReducer(begin(),{type:"settled",key:"a",run:1,ok:false}).phase).toBe("failed");
    const cancelled = launchReducer(begin(),{type:"cancel"});
    expect(launchReducer(cancelled,{type:"settled",key:"a",run:1,ok:true}).phase).toBe("cancelled");
  });
  it("ignores old request keys and old run timers", () => {
    const newer = launchReducer(begin(),{type:"launch",key:"b"});
    expect(launchReducer(newer,{type:"settled",key:"a",run:1,ok:true})).toEqual(newer);
    expect(launchReducer(newer,{type:"advance",run:1})).toEqual(newer);
    expect(launchReducer(newer,{type:"settled",key:"a",run:2,ok:true})).toEqual(newer);
  });
  it("skips decorative flight and docking under reduced motion", () => {
    mockMatchMedia({"(prefers-reduced-motion: reduce)":true});
    const {result,rerender} = renderHook(({busy})=>useLaunchSequence(busy,false,"a",!busy),{initialProps:{busy:true}});
    act(()=>result.current.launch("a")); expect(result.current.phase).toBe("holding");
    const {container} = render(<LaunchCraft phase={result.current.phase} run={1} reduced origin={{current:null}} destination={{current:null}}/>);
    expect(container.querySelector(".mission-flight")).toBeNull();
    rerender({busy:false}); expect(result.current.phase).toBe("completed");
  });
  it("cleans up phase timers and holds for a slow response", () => {
    vi.useFakeTimers(); mockMatchMedia({});
    const {result,unmount} = renderHook(()=>useLaunchSequence(true,false,"a",false));
    act(()=>result.current.launch("a"));
    for (const duration of [PHASE_MS.ignition,PHASE_MS.liftoff,PHASE_MS.transit]) act(()=>vi.advanceTimersByTime(duration));
    expect(result.current.phase).toBe("holding");
    act(()=>result.current.cancel()); expect(result.current.phase).toBe("cancelled");
    unmount(); expect(vi.getTimerCount()).toBe(0);
  });
});

describe("scientific summaries", () => {
  it("qualifies direction words for non-significant and descriptive results", () => {
    expect(discoveryHeadline(analysis())).toBe("An upward slope in air temperature (2 m), but the evidence is inconclusive.");
    const desc = analysis({ trend: { ...analysis().trend!, result_level: "descriptive_slope", mann_kendall: null, slope: -0.1 } });
    expect(discoveryHeadline(desc)).toMatch(/^A downward slope .*without a significance test\.$/);
    const sig = analysis({ trend: { ...analysis().trend!, mann_kendall: { ...analysis().trend!.mann_kendall!, is_statistically_significant: true } } });
    expect(discoveryHeadline(sig)).toBe("An upward signal in air temperature (2 m), indicated by the trend test.");
    expect(discoveryHeadline(analysis({ trend: null }))).toMatch(/isn’t enough reliable data/);
  });

  it("keeps acronyms intact mid-sentence", () => {
    const a = analysis({ variable: { ...analysis().variable, name: "NDVI" } });
    expect(discoveryHeadline(a)).toContain("slope in NDVI");
  });

  it("derives fitted-line change from slope and eligible span only", () => {
    expect(fittedChange(analysis())).toEqual({ value: 0.02 * 9, from: 2015, to: 2024 });
    expect(fittedChange(analysis({ trend: { ...analysis().trend!, slope: null } }))).toBeNull();
  });

  it("explains whether the interval includes zero", () => {
    expect(intervalReading(analysis())).toMatch(/includes zero/);
    expect(intervalReading(analysis({ trend: { ...analysis().trend!, confidence_interval: [0.01, 0.05] } }))).toMatch(/consistently positive/);
  });
});

describe("Explore launch and result identity", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    mockMatchMedia({});
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes("/api/v2/variables")) return new Response(JSON.stringify({ variables: [VARIABLE, NDVI], caveats: [], api_version: "2" }), { status: 200 });
      if (url.includes("/api/v2/analysis")) return new Response(JSON.stringify(analysis()), { status: 200 });
      return new Response("{}", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  async function renderApp() {
    const { default: App } = await import("./App");
    return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><App /></QueryClientProvider>);
  }

  it("shows the result without waiting for the launch animation", async () => {
    const { container } = await renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "Launch investigation" }));
    expect(container.querySelector(".mission-flight")).not.toBeNull();
    // The finding is rendered while the craft is still in flight (well under LIFTOFF_MS).
    expect(await screen.findByRole("heading", { name: /evidence is inconclusive/ }, { timeout: 800 })).toBeInTheDocument();
  });

  it("aborts the launch and shows the error when the request fails", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes("/api/v2/variables")) return new Response(JSON.stringify({ variables: [VARIABLE], caveats: [], api_version: "2" }), { status: 200 });
      return new Response(JSON.stringify({ detail: { reason: "outside_dataset_coverage", message: "Outside coverage" } }), { status: 422 });
    });
    const { container } = await renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "Launch investigation" }));
    expect(await screen.findByText("Not available at this location")).toBeInTheDocument();
    await waitFor(() => expect(container.querySelector(".mission-flight")).toBeNull());
  });

  it("keeps findings tied to the launched request when controls change", async () => {
    await renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "Launch investigation" }));
    await screen.findByRole("heading", { name: /air temperature/ });
    await userEvent.click(screen.getByRole("radio", { name: /NDVI/ }));
    expect(screen.getByText(/Controls changed since this investigation/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /air temperature/ })).toBeInTheDocument();
  });

  it("switches and persists the theme from the header", async () => {
    await renderApp();
    await screen.findByRole("button", { name: "Launch investigation" });
    expect(document.documentElement.dataset.theme).toBe("dark");
    await userEvent.click(screen.getByRole("button", { name: /Switch to Mission Briefing/ }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_KEY)).toBe("light");
    expect(screen.getByRole("button", { name: /Switch to Orbit/ })).toBeInTheDocument();
  });

  it("shows Living Environment as planned, not as a link", async () => {
    await renderApp();
    await screen.findByRole("button", { name: "Launch investigation" });
    expect(screen.queryByRole("link", { name: /Living Environment/ })).toBeNull();
    expect(screen.getByText(/not yet available/)).toBeInTheDocument();
  });
});
