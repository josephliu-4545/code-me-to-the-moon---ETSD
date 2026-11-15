import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";
import catalogText from "../public/snapshots/variables.json?raw";
import snapshotText from "../public/snapshots/yangon-2015-2024-temperature.json?raw";

vi.mock("./components/MapView", () => ({ default: () => <div>Earth map</div> }));
vi.mock("./state/useAnalysis", () => ({
  useVariables: () => ({ data: JSON.parse(catalogText), isPending: false, isError: false }),
  useAnalysis: vi.fn(() => ({ data: undefined, isPending: false, isFetching: false, isError: false })),
  findSnapshot: async () => ({ ...JSON.parse(snapshotText), data_status: "saved_snapshot", snapshot: { captured_at: "2026-11-13", note: "Saved retrieval" } }),
}));
afterEach(() => { window.history.replaceState(null, "", "/"); vi.clearAllMocks(); });

it("opens both dedicated navigation pages and preserves the selected snapshot between them", async () => {
  window.history.replaceState(null, "", "/#history");
  render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);
  expect(screen.getByRole("link", { name: "Historical Discovery" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Mission Findings" })).toHaveAttribute("href", "#findings");
  await userEvent.click(screen.getByRole("button", { name: "View saved Yangon example" }));
  expect(await screen.findByRole("heading", { name: "Annual values and fitted trend" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("link", { name: "Mission Findings" }));
  expect(await screen.findByRole("heading", { name: /evidence is inconclusive/ })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Explore the supporting observations" })).toHaveAttribute("href", "#history");
  expect(screen.getAllByText(/Saved snapshot of a live NASA retrieval/).length).toBeGreaterThan(0);
  await userEvent.click(screen.getByRole("link", { name: "Historical Discovery" }));
  expect(await screen.findByRole("heading", { name: "Annual values and fitted trend" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "View saved Yangon example" })).not.toBeInTheDocument();
});

it.each(["history", "findings"])("keeps location selection on Explore Earth for the %s page", async (section) => {
  window.history.replaceState(null, "", `/#${section}`);
  render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);
  expect(screen.queryByLabelText("Latitude")).not.toBeInTheDocument();
  expect(screen.queryByRole("radiogroup", { name: "Environmental variable" })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Choose location and signal" })).toHaveAttribute("href", "#explore");
  await userEvent.click(screen.getByRole("link", { name: "Choose location and signal" }));
  expect(await screen.findByLabelText("Latitude")).toBeInTheDocument();
  expect(window.location.hash).toBe("#explore");
});
