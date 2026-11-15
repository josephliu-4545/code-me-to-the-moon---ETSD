import { expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { boxCorners, boxFromCorners, boxPatch, boxProblem, circleProblem, distanceKm, moveBox, regionLimits } from "./lib/region";
import { circlePolygon, splitAtDateline } from "./lib/geometry";
import { DEFAULT_SELECTION, parseSelection, patchSelection, requestIdentity, selectionBox, serializeSelection, toRequest } from "./state/selection";
import RegionBounds from "./components/explore/RegionBounds";
import type { Analysis, VariableInfo } from "./api/types";
import { footprintFor, selectionDiffers } from "./pages/ExplorePage";
import { validateSelection } from "./components/AnalysisControls";

const info = { id: "precipitation", available_from: "2000-01-01", max_years: 30, modes: { point: true, region: true }, region_shape: "bbox", min_region_span_degrees: 0.1, max_region_span_degrees: 3 } as VariableInfo;
const s = { ...DEFAULT_SELECTION, variable: "precipitation" as const, mode: "region" as const, bbox: [95,16,97,17] as [number,number,number,number] };
it("normalizes all corner orders and preserves non-square bounds", () => {
  expect(boxFromCorners([97,16],[95,17])).toEqual(s.bbox);
  expect(boxFromCorners([95,17],[97,16])).toEqual(s.bbox);
  expect(boxCorners(s.bbox)).toEqual([[95,16],[97,16],[97,17],[95,17]]);
  expect(moveBox(s.bbox, 100,20)).toEqual([99,19.5,101,20.5]);
});
it("enforces catalog dimensions and rejects invalid or crossing boxes without clipping", () => {
  const limits = regionLimits(info)!;
  expect(limits.max).toBe(3);
  expect(boxProblem([0,0,0.1,0.1], limits)).toBeNull();
  expect(boxProblem([0,0,3,3], limits)).toBeNull();
  for (const b of [[0,0,0.09,1], [0,0,4,1], [179,0,-179,1], [179,0,181,1], [0,89,1,91], [0,0,NaN,1]])
    expect(boxProblem(b as typeof s.bbox,limits)).not.toBeNull();
  expect(validateSelection(info, {...s, latitude:89.8, longitude:179.9, bbox:undefined})).toMatch(/Dateline/);
  expect(regionLimits(undefined)).toBeNull();
});
it("serializes bounds and invalidates only relevant scientific identities", () => {
  expect(toRequest(s).bbox).toEqual(s.bbox);
  expect(parseSelection(serializeSelection(s)).bbox).toEqual(s.bbox);
  const moved = patchSelection(s, boxPatch(moveBox(s.bbox, 100,20)));
  expect(selectionBox(moved)).toEqual([99,19.5,101,20.5]);
  expect(requestIdentity(toRequest(moved))).not.toBe(requestIdentity(toRequest(s)));
  expect(toRequest({...s,mode:"point"}).bbox).toBeUndefined();
  expect(toRequest({...s,variable:"ndvi"}).bbox).toBeUndefined();
  expect(patchSelection(s,{longitude:110}).bbox).toBeUndefined();
  expect(patchSelection(s,{startYear:2016}).bbox).toEqual(s.bbox);
});
it.each([0, 70, -70])("constructs a geodesic 50 km circle at latitude %s", lat => {
  const ring = circlePolygon(lat,179.9,50);
  for (const p of ring) expect(distanceKm([179.9,lat],p)).toBeCloseTo(50,7);
  expect(ring[0]![0]).toBeCloseTo(ring.at(-1)![0],9);
  expect(splitAtDateline(ring)).toHaveLength(2);
  expect(circleProblem(lat,50,100)).toBeNull();
});
it("rejects invalid radii and explicitly restricts pole-enclosing display geometry", () => {
  expect(circleProblem(89.9,50,100)).toMatch(/pole/);
  expect(circleProblem(0,101,100)).toMatch(/at most/);
  expect(circleProblem(0,NaN,100)).not.toBeNull();
});
it("keeps returned support separate from a changed draft and preserves approximate source cells", () => {
  const result = { spatial_support: { bbox: {west:95,south:16,east:97,north:17}, resolution:"IMERG area-weighted pixels" } } as Analysis;
  expect(footprintFor(s,result)?.bounds).toEqual(result.spatial_support.bbox);
  const changed = {...s,bbox:[95,16,98,18] as typeof s.bbox};
  expect(selectionDiffers(changed,toRequest(s))).toBe(true);
  expect(footprintFor(changed,undefined)?.bounds).toEqual({west:95,south:16,east:98,north:18});
  const cell = { spatial_support: {cell:{bounds:{west:95,south:16,east:96,north:17},approximate:true},resolution:"Approximate POWER cell"} } as Analysis;
  expect(footprintFor(DEFAULT_SELECTION,cell)?.approximate).toBe(true);
  expect(selectionDiffers({...DEFAULT_SELECTION,variable:"soil_moisture",dataset:"smap_l3e_v006_am"},toRequest({...DEFAULT_SELECTION,variable:"soil_moisture",dataset:"smap_l3e_v005_am"}))).toBe(true);
  expect(validateSelection({...info,modes:{point:true,region:false},region_unsupported_reason:"Native cell only."},{...s,variable:"temperature"})).toBe("Native cell only.");
});
it("applies accessible numerical bounds and reports invalid dimensions", async () => {
  const change = vi.fn(); const user = userEvent.setup();
  render(<RegionBounds selection={s} info={info} onChange={change}/>);
  const east = screen.getByLabelText("East (degrees)");
  await user.clear(east); await user.type(east,"99");
  await user.click(screen.getByRole("button",{name:"Apply bounds"}));
  expect(change).not.toHaveBeenCalled();
  expect(screen.getByRole("status")).toHaveTextContent("0.1–3");
  await user.clear(east); await user.type(east,"98");
  await user.click(screen.getByRole("button",{name:"Apply bounds"}));
  expect(change).toHaveBeenCalledWith(boxPatch([95,16,98,17]));
});
