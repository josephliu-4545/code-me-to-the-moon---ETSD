/**
 * Phase 3: offline demo integrity and reload behaviour.
 * The real committed snapshots are served to the app while every /api/ request fails, then the same
 * saved investigation is followed through Explore, Scientific Evaluation (and its Methods Lab),
 * Feature 01 and the AI Earth Detective.
 */
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Analysis } from "./api/types";
import MissionFindings from "./components/expedition/MissionFindings";
import { LAST_INVESTIGATION_KEY, parseStoredInvestigation } from "./state/investigation";

const RAW = import.meta.glob("../public/snapshots/*.json", { eager: true, query: "?raw", import: "default" }) as Record<string, string>;
const file = (name: string) => RAW[`../public/snapshots/${name}`]!;
const INDEX = JSON.parse(file("index.json")) as { captured_at: string };
const CAPTURED = INDEX.captured_at;

function offlineFetch(apiCalls: string[]) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/")) {
      apiCalls.push(url);
      throw new TypeError("Failed to fetch"); // backend unreachable
    }
    const name = url.split("snapshots/")[1];
    if (name && RAW[`../public/snapshots/${name}`]) return new Response(file(name), { status: 200 });
    return new Response("", { status: 404 });
  });
}

async function renderApp(search = "/?lat=16.8661&lon=96.1951&v=temperature&from=2015&to=2024&mode=point&place=Yangon%2C+Myanmar") {
  window.history.replaceState(null, "", search);
  const { default: App } = await import("./App");
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><App /></QueryClientProvider>);
}

const go = async (hash: string) => act(async () => { window.location.hash = hash; window.dispatchEvent(new HashChangeEvent("hashchange")); });

beforeEach(() => window.sessionStorage.clear());
afterEach(() => { vi.unstubAllGlobals(); window.location.hash = ""; });

describe("offline demo walkthrough with the refreshed snapshots", () => {
  it("shows one saved investigation consistently on every page, labelled as a snapshot", async () => {
    const apiCalls: string[] = [];
    vi.stubGlobal("fetch", offlineFetch(apiCalls));
    const user = userEvent.setup();
    await renderApp();
    expect(await screen.findByText(/Offline mode/)).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "Launch investigation" }));
    await user.click(await screen.findByRole("button", { name: "Show saved snapshot" }));
    const label = new RegExp(`Saved snapshot of a live NASA retrieval \\(captured ${CAPTURED.replace(/[+]/g, "\\+")}\\)`);
    expect((await screen.findAllByText(label)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\+0\.0205/).length).toBeGreaterThan(0);

    await go("#evaluation");
    expect(await screen.findByText(/Evidence review/)).toBeInTheDocument();
    expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Statistical Methods Lab" }));
    await user.click(screen.getByRole("tab", { name: "OLS vs Theil–Sen" }));
    expect(screen.getByTestId("estimator-table")).toHaveTextContent("+0.0295");
    expect(screen.getByTestId("estimator-table")).toHaveTextContent("+0.0205");

    await go("#detective");
    expect(await screen.findByTestId("evidence-panel")).toHaveTextContent(/Saved snapshot/);
    await user.type(screen.getByRole("textbox", { name: "Your question" }), "How much has it changed?{Enter}");
    const answer = within(screen.getByRole("log")).getAllByRole("article").pop()!;
    expect(answer).toHaveTextContent("0.0205");
    expect(answer).toHaveTextContent(new RegExp(`saved snapshot of an earlier live NASA retrieval \\(captured ${CAPTURED.replace(/[+]/g, "\\+")}\\)`));
    expect(apiCalls.every((u) => !u.includes("snapshot"))).toBe(true);
  });

  it("the Detective and Evaluation offer the same saved snapshot when opened first", async () => {
    vi.stubGlobal("fetch", offlineFetch([]));
    const user = userEvent.setup();
    await renderApp();
    await user.click(await screen.findByRole("button", { name: "Launch investigation" }));
    await screen.findByRole("button", { name: "Show saved snapshot" });
    await go("#detective");
    await user.click(await screen.findByRole("button", { name: "Show saved snapshot" }));
    expect(await screen.findByTestId("evidence-panel")).toHaveTextContent(/Saved snapshot/);
    await go("#evaluation");
    // Loaded once (App state), reused here without another click.
    expect(await screen.findByText(/Evidence review/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show saved snapshot" })).toBeNull();
  });
});

describe("reload: saved selection versus executed investigation", () => {
  const stored = { request: { variable: "ndvi", latitude: 16.8661, longitude: 96.1951, startYear: 2015, endYear: 2025, mode: "point" }, place: "Yangon, Myanmar" };

  it("a shared URL alone never runs an analysis", async () => {
    const apiCalls: string[] = [];
    vi.stubGlobal("fetch", offlineFetch(apiCalls));
    await renderApp();
    await screen.findByRole("button", { name: "Launch investigation" });
    expect(apiCalls.filter((u) => u.includes("/api/v2/analysis"))).toEqual([]);
    expect(screen.queryByRole("region", { name: "Previous investigation" })).toBeNull();
  });

  it("after a reload the last investigation is offered, and only an explicit click requests it", async () => {
    window.sessionStorage.setItem(LAST_INVESTIGATION_KEY, JSON.stringify(stored));
    const apiCalls: string[] = [];
    vi.stubGlobal("fetch", offlineFetch(apiCalls));
    const user = userEvent.setup();
    await renderApp();
    const banner = await screen.findByRole("region", { name: "Previous investigation" });
    expect(banner).toHaveTextContent(/Yangon, Myanmar · ndvi · 2015–2024/);
    expect(banner).toHaveTextContent(/not re-requested automatically/);
    expect(apiCalls.filter((u) => u.includes("/api/v2/analysis"))).toEqual([]);
    await user.click(within(banner).getByRole("button", { name: "Resume investigation" }));
    expect(apiCalls.filter((u) => u.includes("/api/v2/analysis") && u.includes("variable=ndvi"))).toHaveLength(1);
    expect(screen.queryByRole("region", { name: "Previous investigation" })).toBeNull();
  });

  it("dismissing forgets it", async () => {
    window.sessionStorage.setItem(LAST_INVESTIGATION_KEY, JSON.stringify(stored));
    vi.stubGlobal("fetch", offlineFetch([]));
    const user = userEvent.setup();
    await renderApp();
    await user.click(await screen.findByRole("button", { name: "Dismiss" }));
    expect(window.sessionStorage.getItem(LAST_INVESTIGATION_KEY)).toBeNull();
  });

  it("launching records the executed investigation for this tab", async () => {
    vi.stubGlobal("fetch", offlineFetch([]));
    const user = userEvent.setup();
    await renderApp();
    await user.click(await screen.findByRole("button", { name: "Launch investigation" }));
    const saved = parseStoredInvestigation(window.sessionStorage.getItem(LAST_INVESTIGATION_KEY));
    expect(saved?.request).toMatchObject({ variable: "temperature", startYear: 2015, endYear: 2025, mode: "point" });
    expect(saved?.place).toBe("Yangon, Myanmar");
  });

  it.each([
    ["not JSON", "{oops"],
    ["unknown variable", JSON.stringify({ request: { ...stored.request, variable: "lava" }, place: "x" })],
    ["impossible latitude", JSON.stringify({ request: { ...stored.request, latitude: 400 }, place: "x" })],
    ["inverted period", JSON.stringify({ request: { ...stored.request, startYear: 2025, endYear: 2015 }, place: "x" })],
    ["bad bbox", JSON.stringify({ request: { ...stored.request, bbox: [1, 2] }, place: "x" })],
  ])("ignores a malformed stored investigation (%s)", (_name, raw) => {
    expect(parseStoredInvestigation(raw)).toBeNull();
  });
});

describe("Feature 01 with the refreshed snapshots", () => {
  const load = (name: string) => JSON.parse(file(name)) as Analysis;

  it("handles the seasonal NDVI snapshot without inventing an annual line", async () => {
    const a = load("yangon-2015-2024-ndvi.json");
    expect(a.trend?.method).toBe("seasonal_kendall");
    const user = userEvent.setup();
    const { container } = render(<MissionFindings analysis={a} />);
    const journey = screen.getByRole("list", { name: "Evidence journey" });
    expect(within(journey).getByRole("button", { name: /Eligible data/ })).toHaveTextContent(/16 monthly values/);
    await user.click(within(journey).getByRole("button", { name: /^Trend/ }));
    expect(container.querySelector(".ep-trend")).toBeNull();
    expect(screen.getAllByText(/qualifying monthly values/).length).toBeGreaterThan(0);
  });

  it("shows temperature with its Theil–Sen line and the unavailable SMAP result without a trend", async () => {
    const user = userEvent.setup();
    const { container, unmount } = render(<MissionFindings analysis={load("yangon-2015-2024-temperature.json")} />);
    await user.click(within(screen.getByRole("list", { name: "Evidence journey" })).getByRole("button", { name: /^Trend/ }));
    expect(container.querySelector(".ep-trend")).not.toBeNull();
    unmount();
    render(<MissionFindings analysis={load("yangon-2015-2024-soil_moisture-smap_l3e_v006_am.json")} />);
    await user.click(within(screen.getByRole("list", { name: "Evidence journey" })).getByRole("button", { name: /^Trend/ }));
    expect(screen.getByText(/No trend line was estimated/)).toBeInTheDocument();
  });
});
