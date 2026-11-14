import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Analysis, RelationshipsResponse, VariableId, VariableInfo } from "./api/types";
import RelationshipsPage from "./pages/RelationshipsPage";
import { DEFAULT_SELECTION } from "./state/selection";

const ids: VariableId[] = ["temperature", "relative_humidity", "extreme_heat", "precipitation", "ndvi", "soil_moisture"];

const variables: VariableInfo[] = ids.map((id) => ({
  id,
  name: id,
  short_name: id.replace(/_/g, " "),
  description: id,
  annual_value: "annual value",
  units: id === "temperature" ? "°C" : "%",
  slope_units: "units/year",
  dataset: { source: "NASA", id, version: "1", provenance: "test", doi: null },
  spatial_resolution: "grid cell",
  temporal_resolution: "annual",
  available_from: "2000-01-01",
  max_years: 30,
  default_period: [2015, 2025],
  modes: { point: true, region: false },
  region_unsupported_reason: null,
}));

function analysis(id: VariableId, units: string): Analysis {
  return {
    variable: { id, name: id, description: id, annual_value_definition: "mean" },
    dataset: { source: "NASA", id, version: "1", provenance: "test", doi: null },
    spatial_support: { mode: "point", type: "grid_cell", description: "grid cell", resolution: "1°", requested: { latitude: 16.8661, longitude: 96.1951 } },
    period: { start: "2015-01-01", end_exclusive: "2025-01-01" },
    units: { annual_value: units, slope: `${units}/year` },
    annual: [], series: [], series_definition: null, trend: null,
    coverage: { years_requested: 10, eligible_years: 2, excluded_years: [] },
    methodology: { source: {}, trend_method: {} }, caveats: [], limitations: [], extra: {}, data_status: "live_nasa_retrieval",
  };
}

const response: RelationshipsResponse = {
  variables: ["temperature", "relative_humidity"],
  results: { temperature: analysis("temperature", "°C"), relative_humidity: analysis("relative_humidity", "%") },
  alignment: { temporal: "shared years", spatial: ["different grid cells"], spatial_supports_differ: true },
  common_eligible_years: [2020, 2021],
  paired_values: [{ year: 2020, temperature: 27, relative_humidity: 75 }, { year: 2021, temperature: 28, relative_humidity: 73 }],
  spearman_rho_annual: -1,
  spearman_rho_first_differences: null,
  unavailable_reasons: ["insufficient_first_differences"],
  interpretation: "Descriptive only; correlation does not imply causation.",
};

describe("Relationships page", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("does not present submitted relationship results as current after a variable changes", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(response), { status: 200 })));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><RelationshipsPage variables={variables} selection={DEFAULT_SELECTION} /></QueryClientProvider>);

    await userEvent.click(screen.getByRole("button", { name: "Compare annual values" }));
    expect(await screen.findByText("Descriptive association")).toBeInTheDocument();

    await userEvent.click(within(screen.getByRole("group", { name: /Variable A/ })).getByRole("radio", { name: "precipitation" }));

    expect(screen.queryByText("Descriptive association")).not.toBeInTheDocument();
  });

  it("allows a replacement relationship request while the obsolete request is still fetching", async () => {
    let resolveFirst!: (value: Response) => void;
    let firstSignal: AbortSignal | undefined;
    let calls = 0;
    vi.stubGlobal("fetch", vi.fn((_url: string, init?: RequestInit) => {
      calls += 1;
      if (calls === 1) {
        firstSignal = init?.signal ?? undefined;
        return new Promise<Response>((resolve) => { resolveFirst = resolve; });
      }
      return Promise.resolve(new Response(JSON.stringify({
        ...response,
        variables: ["extreme_heat", "relative_humidity"],
        results: { extreme_heat: analysis("extreme_heat", "%"), relative_humidity: analysis("relative_humidity", "%") },
        interpretation: "Current replacement response.",
      }), { status: 200 }));
    }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><RelationshipsPage variables={variables} selection={DEFAULT_SELECTION} /></QueryClientProvider>);

    await userEvent.click(screen.getByRole("button", { name: "Compare annual values" }));
    await userEvent.click(within(screen.getByRole("group", { name: /Variable A/ })).getByRole("radio", { name: "extreme heat" }));

    const replacement = screen.getByRole("button", { name: "Compare annual values" });
    expect(replacement).toBeEnabled();
    await userEvent.click(replacement);
    expect(firstSignal?.aborted).toBe(true);
    expect(await screen.findByText("Current replacement response.")).toBeInTheDocument();

    resolveFirst(new Response(JSON.stringify({ ...response, interpretation: "Obsolete response." }), { status: 200 }));
    await waitFor(() => expect(screen.queryByText("Obsolete response.")).not.toBeInTheDocument());
    expect(screen.getByText("Current replacement response.")).toBeInTheDocument();
  });
});
