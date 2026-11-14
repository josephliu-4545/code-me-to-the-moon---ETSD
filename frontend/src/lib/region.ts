import type { VariableInfo } from "../api/types";

export type Box = [west: number, south: number, east: number, north: number];
export interface RegionLimits { min: number; max: number }
export const regionLimits = (info?: VariableInfo): RegionLimits | null =>
  info?.modes.region && info.region_shape === "bbox" && info.min_region_span_degrees != null && info.max_region_span_degrees != null
    ? { min: info.min_region_span_degrees, max: info.max_region_span_degrees } : null;

export function boxProblem(b: Box, limits: RegionLimits): string | null {
  const [w, s, e, n] = b;
  if (!b.every(Number.isFinite)) return "Enter four finite bounds.";
  if (w < -180 || e > 180 || s < -90 || n > 90 || w >= e || s >= n)
    return "Use west < east and south < north within ±180° longitude and ±90° latitude. Dateline crossing is unsupported.";
  const width = e - w, height = n - s;
  if (width < limits.min - 1e-9 || height < limits.min - 1e-9 || width > limits.max + 1e-9 || height > limits.max + 1e-9)
    return `Width and height must each be ${limits.min}–${limits.max}°.`;
  return null;
}

/** Ordering only: never clamp, wrap, or silently shrink the user's region. */
export function boxFromCorners(a: [number, number], b: [number, number]): Box {
  return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];
}
export function boxCorners([w, s, e, n]: Box): [number, number][] { return [[w,s], [e,s], [e,n], [w,n]]; }
export function moveBox(b: Box, lon: number, lat: number): Box {
  const dx = lon - (b[0] + b[2]) / 2, dy = lat - (b[1] + b[3]) / 2;
  return [b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy];
}
export function boxPatch(bbox: Box) {
  return { bbox, longitude: (bbox[0] + bbox[2]) / 2, latitude: (bbox[1] + bbox[3]) / 2, placeName: "" };
}
export function distanceKm(a: [number, number], b: [number, number]): number {
  const rad = Math.PI / 180, dlat = (b[1]-a[1])*rad, dlon = (b[0]-a[0])*rad;
  const h = Math.sin(dlat/2)**2 + Math.cos(a[1]*rad)*Math.cos(b[1]*rad)*Math.sin(dlon/2)**2;
  return 6371.0088 * 2 * Math.asin(Math.sqrt(Math.min(1, h)));
}
export function circleProblem(lat: number, radius: number, max: number): string | null {
  if (!Number.isFinite(radius) || radius <= 0 || radius > max) return `Radius must be greater than zero and at most ${max} km.`;
  // The backend can buffer at the poles, but our geographic ring renderer cannot represent a pole-enclosing ring.
  if (Math.abs(lat) + radius / 6371.0088 * 180 / Math.PI >= 90) return "This map editor does not support circles enclosing a pole. Move the center or reduce the radius.";
  return null;
}
