import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { it, expect, vi } from "vitest";
import { DEFAULT_SELECTION, toRequest, requestIdentity } from "./state/selection";
import { validateAnalysis } from "./api/client";
import { splitAtDateline } from "./lib/geometry";
import { yearLimits } from "./components/AnalysisControls";
import LocationPanel from "./components/LocationPanel";
import { MapUnavailable } from "./components/explore/MapBoundary";
import type { VariableInfo } from "./api/types";

it("canonicalizes only the parameters actually sent to analysis", () => {
 const a = toRequest(DEFAULT_SELECTION);
 const b = toRequest({ ...DEFAULT_SELECTION, dataset: "unused", radiusKm: 90, placeName: "new label" });
 expect(requestIdentity(a)).toBe(requestIdentity(b));
 expect(requestIdentity(a)).not.toBe(requestIdentity(toRequest({ ...DEFAULT_SELECTION, longitude: 1 })));
 const circle = { ...DEFAULT_SELECTION, variable: "ndvi" as const, mode: "region" as const };
 expect(requestIdentity(toRequest(circle))).not.toBe(requestIdentity(toRequest({ ...circle, radiusKm: 9 })));
});
it("splits a dateline crossing into small closed polygons", () => {
 const parts = splitAtDateline([[179,1],[-179,1],[-179,-1],[179,-1],[179,1]]);
 expect(parts).toHaveLength(2);
 for (const ring of parts) {
   expect(ring[0]).toEqual(ring[ring.length - 1]);
   expect(Math.max(...ring.map(([x]) => x)) - Math.min(...ring.map(([x]) => x))).toBeLessThanOrEqual(2);
 }
});
it("rejects malformed scientific responses", () => {
 expect(() => validateAnalysis({ annual: [{ year: 2020, value: NaN }] })).toThrow(/invalid scientific response/);
});
it("uses authoritative product dates over legacy UI metadata", () => {
 const info = { available_from: "2000-01-01", max_years: 27, products: [{ key: "smap_l3e_v006_am", availability: { documented_first: "2017-03-01", documented_last: null, latest_observation: "2024-10-01" } }] } as VariableInfo;
 expect(yearLimits(info, { ...DEFAULT_SELECTION, variable: "soil_moisture", dataset: "smap_l3e_v006_am" })).toEqual({ min: 2017, max: 2024, maxYears: 27 });
});
it("keeps coordinate entry usable without the globe and rejects blanks", async () => {
 const onChange = vi.fn(), retry = vi.fn();
 render(<QueryClientProvider client={new QueryClient()}><MapUnavailable onRetry={retry} /><LocationPanel latitude={0} longitude={0} placeName="" onChange={onChange}/></QueryClientProvider>);
 await userEvent.clear(screen.getByLabelText("Latitude"));
 await userEvent.click(screen.getByRole("button", { name: "Set" }));
 expect(screen.getByText(/Latitude must be between/)).toBeInTheDocument();
 expect(onChange).not.toHaveBeenCalled();
 await userEvent.click(screen.getByRole("button", { name: "Restart globe" }));
 expect(retry).toHaveBeenCalledOnce();
});
