import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Analysis, VariablesResponse } from "./api/types";
import { planInvestigationQuestion } from "./detective/planner";

vi.mock("./components/MapView", () => ({ default: () => <div>Map ready</div> }));

const SNAPSHOTS = import.meta.glob("../public/snapshots/*.json", { eager: true, import: "default" }) as Record<string, unknown>;
const variables = SNAPSHOTS["../public/snapshots/variables.json"] as VariablesResponse;
const precipitation = structuredClone(SNAPSHOTS["../public/snapshots/yangon-2015-2024-precipitation.json"]) as Analysis;

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

describe("completed feature journeys", () => {
  it("plans a supported natural-language investigation without inventing values", () => {
    expect(planInvestigationQuestion("Has precipitation changed in Singapore?", variables.variables)).toEqual({
      variable: "precipitation", placeQuery: "Singapore", startYear: 2015, endYearInclusive: 2024, dataset: undefined,
    });
    expect(planInvestigationQuestion("Tell me something about Earth", variables.variables)).toBeNull();
    expect(planInvestigationQuestion("How did rainfall change in Singapore from 1990 to 2025?", variables.variables)).toBeNull();
  });

  it("turns the question into a geocoded real analysis request", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input); calls.push(url);
      if (url.includes("/api/v2/variables")) return new Response(JSON.stringify(variables), { status: 200 });
      if (url.includes("/api/v2/geocode")) return new Response(JSON.stringify({ results: [{ name: "Singapore", latitude: 1.3521, longitude: 103.8198 }] }), { status: 200 });
      if (url.includes("/api/v2/analysis")) {
        const body = structuredClone(precipitation);
        body.spatial_support.requested = { latitude: 1.3521, longitude: 103.8198 };
        return new Response(JSON.stringify(body), { status: 200 });
      }
      return new Response("", { status: 404 });
    }));
    const { default: App } = await import("./App");
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><App /></QueryClientProvider>);
    await userEvent.click(await screen.findByRole("link", { name: "AI Earth Detective" }));
    const input = await screen.findByRole("textbox", { name: "Your question" });
    await userEvent.type(input, "Has precipitation changed in Singapore?");
    await userEvent.click(screen.getByRole("button", { name: "Investigate" }));
    await waitFor(() => expect(calls.some((url) => url.includes("/api/v2/analysis") && url.includes("variable=precipitation") && url.includes("latitude=1.3521") && url.includes("longitude=103.8198"))).toBe(true));
  });

});
