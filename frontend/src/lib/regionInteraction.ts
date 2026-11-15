import { Marker, type Map as MLMap } from "maplibre-gl";
import { boxCorners, boxProblem, circleProblem, distanceKm, moveBox, type Box, type RegionLimits } from "./region";

export type EditableRegion = { kind: "box"; bounds: Box; limits: RegionLimits } |
  { kind: "circle"; center: [number, number]; radiusKm: number; maxRadius: number };

/** Markers are geographic handles; the selection itself is a GeoJSON polygon. */
export function attachRegionHandles(map: MLMap, initial: EditableRegion,
  update: (region: EditableRegion) => void, message: (text: string) => void,
  active: (value: boolean) => void) {
  let region = initial;
  let start = initial;
  let frame = 0;
  let pending: EditableRegion | null = null;
  let pan = false, rotate = false, zoom = false;
  let dragging = false;
  const markers: Marker[] = [];
  function positions(r: EditableRegion): [number, number][] {
    if (r.kind === "box") return [...boxCorners(r.bounds), [(r.bounds[0]+r.bounds[2])/2, (r.bounds[1]+r.bounds[3])/2]];
    // Due north is an exact great-circle radius handle; pole-enclosing circles are rejected.
    return [[r.center[0], r.center[1] + r.radiusKm / 6371.0088 * 180 / Math.PI], r.center];
  }
  function sync() { positions(region).forEach((p,i) => markers[i]?.setLngLat(p)); }
  function flush() { if (pending) { update(pending); pending = null; } }
  function restore() {
    if (!dragging) return;
    dragging = false;
    if (pan) map.dragPan.enable();
    if (rotate) map.dragRotate.enable();
    if (zoom) map.touchZoomRotate.enable();
    markers.forEach(m => m.getElement().classList.remove("is-dragging"));
    active(false);
  }
  function cancel() { if (!dragging) return; cancelAnimationFrame(frame); pending = null; region = start; update(start); sync(); restore(); }
  const escape = (e: KeyboardEvent) => { if (e.key === "Escape") cancel(); };
  positions(initial).forEach((position, i, points) => {
    const center = i === points.length - 1;
    const el = document.createElement("button"); el.type = "button";
    el.className = `region-handle ${center ? "region-center" : ""}`;
    el.setAttribute("aria-label", center ? "Move region center; arrow keys adjust" : initial.kind === "box" ? `Resize corner ${i+1}; arrow keys adjust` : "Adjust radius; arrow keys adjust");
    const marker = new Marker({ element: el, draggable: true, clickTolerance: 4 }).setLngLat(position).addTo(map);
    markers.push(marker);
    function change(lon: number, lat: number) {
      let next: EditableRegion;
      let error: string | null;
      if (region.kind === "box") {
        const bounds: Box = center ? moveBox(region.bounds, lon, lat) : [...region.bounds];
        // Keep each handle's identity and opposite corner fixed; do not flip across the other corner.
        if (!center) { bounds[i === 0 || i === 3 ? 0 : 2] = lon; bounds[i < 2 ? 1 : 3] = lat; }
        error = boxProblem(bounds, region.limits); next = { ...region, bounds };
      } else {
        next = center ? { ...region, center: [lon,lat] } : { ...region, radiusKm: distanceKm(region.center, [lon,lat]) };
        error = lon < -180 || lon > 180 || lat < -90 || lat > 90 ? "Keep the center within geographic bounds." : circleProblem(next.center[1], next.radiusKm, next.maxRadius);
      }
      if (error) { message(error); sync(); return; }
      region = next; pending = next; sync();
      cancelAnimationFrame(frame); frame = requestAnimationFrame(flush);
      message("Selection updated. Launch again to analyse this area.");
    }
    marker.on("dragstart", () => {
      start = region; dragging = true; active(true); el.classList.add("is-dragging");
      pan = map.dragPan.isEnabled(); rotate = map.dragRotate.isEnabled(); zoom = map.touchZoomRotate.isEnabled();
      map.dragPan.disable(); map.dragRotate.disable(); map.touchZoomRotate.disable();
    });
    marker.on("drag", () => { if (!dragging) return; const p = marker.getLngLat(); change(p.lng, p.lat); });
    marker.on("dragend", () => { cancelAnimationFrame(frame); flush(); sync(); restore(); });
    el.addEventListener("click", e => e.stopPropagation());
    el.addEventListener("keydown", e => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
      e.preventDefault(); e.stopPropagation(); active(true);
      const p = marker.getLngLat(), step = e.shiftKey ? 0.1 : 0.01;
      change(p.lng + (e.key === "ArrowLeft" ? -step : e.key === "ArrowRight" ? step : 0), p.lat + (e.key === "ArrowDown" ? -step : e.key === "ArrowUp" ? step : 0));
      cancelAnimationFrame(frame); flush(); active(false);
    });
  });
  window.addEventListener("keydown", escape);
  window.addEventListener("blur", cancel);
  return {
    sync(next: EditableRegion) { region = next; sync(); },
    dispose() { cancelAnimationFrame(frame); restore(); markers.forEach(m => m.remove()); window.removeEventListener("keydown", escape); window.removeEventListener("blur", cancel); },
  };
}
