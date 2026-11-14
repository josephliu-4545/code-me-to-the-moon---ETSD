import {
  ApiError,
  type Analysis,
  type AnalysisRequest,
  type GeocodeResult,
  type RelationshipsResponse,
  type SoilMoistureCompare,
  type VariableId,
  type VariablesResponse,
} from "./types";

import { readAccessKey } from "../state/accessKey";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "";

function describe(detail: unknown): { message: string; reason?: string } {
  if (typeof detail === "string") return { message: detail };
  if (detail && typeof detail === "object") {
    const d = detail as { message?: unknown; reason?: unknown };
    if (typeof d.message === "string") return { message: d.message, reason: typeof d.reason === "string" ? d.reason : undefined };
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string; loc?: unknown[] } | undefined;
      if (first?.msg) return { message: `${first.msg}${first.loc ? ` (${first.loc.slice(1).join(".")})` : ""}` };
    }
  }
  return { message: "Request failed" };
}

export async function getJson<T>(path: string, params: Record<string, string | number | undefined>, signal?: AbortSignal): Promise<T> {
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") query.set(k, String(v));
  let response: Response;
  try {
    const key = readAccessKey();
    response = await fetch(`${BASE}${path}${query.size ? `?${query}` : ""}`, { signal, headers: key ? { "X-API-Key": key } : undefined });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, "The backend could not be reached. Check that the API server is running.");
  }
  let body: unknown = null;
  let json = true;
  try {
    body = await response.json();
  } catch {
    json = false;
  }
  if (!response.ok) {
    if (!json) throw new ApiError(response.status, "The analysis service did not respond correctly. It may be offline.", undefined, false);
    const { message, reason } = describe((body as { detail?: unknown } | null)?.detail);
    throw new ApiError(response.status, message, reason);
  }
  if (path === "/api/v2/analysis") validateAnalysis(body);
  return body as T;
}

export const api = {
  variables: (signal?: AbortSignal, verify = false) => getJson<VariablesResponse>("/api/v2/variables", verify ? { verify_availability: "true" } : {}, signal),
  analysis: (r: AnalysisRequest, signal?: AbortSignal) =>
    getJson<Analysis>(
      "/api/v2/analysis",
      {
        variable: r.variable,
        latitude: r.latitude,
        longitude: r.longitude,
        start_date: `${r.startYear}-01-01`,
        end_date: `${r.endYear}-01-01`,
        mode: r.mode,
        radius_km: r.variable === "ndvi" && r.mode === "region" ? r.radiusKm : undefined,
        dataset: r.variable === "soil_moisture" ? r.dataset : undefined,
        bbox: r.bbox ? r.bbox.map((v) => v.toFixed(4)).join(",") : undefined,
      },
      signal,
    ),
  relationships: (
    a: VariableId,
    b: VariableId,
    lat: number,
    lon: number,
    startYear: number,
    endYear: number,
    soilDataset?: string,
    signal?: AbortSignal,
  ) =>
    getJson<RelationshipsResponse>(
      "/api/v2/relationships",
      {
        variables: `${a},${b}`,
        latitude: lat,
        longitude: lon,
        start_date: `${startYear}-01-01`,
        end_date: `${endYear}-01-01`,
        soil_moisture_dataset: a === "soil_moisture" || b === "soil_moisture" ? soilDataset : undefined,
      },
      signal,
    ),
  soilMoistureCompare: (datasets: string[], lat: number, lon: number, startYear: number, endYear: number, signal?: AbortSignal) =>
    getJson<SoilMoistureCompare>(
      "/api/v1/soil-moisture/compare",
      {
        datasets: datasets.join(","),
        latitude: lat,
        longitude: lon,
        start_date: `${startYear}-01-01`,
        end_date: `${endYear}-01-01`,
      },
      signal,
    ),
  geocode: (q: string, signal?: AbortSignal) =>
    getJson<{ results: GeocodeResult[]; attribution?: string }>("/api/v2/geocode", { q }, signal),
};

/** Reject malformed scientific payloads rather than displaying invented defaults. */
export function validateAnalysis(body: unknown): asserts body is Analysis {
  const bad = () => { throw new ApiError(502, "The service returned an invalid scientific response. No findings were accepted.", "invalid_analysis_response"); };
  if (!body || typeof body !== "object") return bad();
  const a = body as Analysis;
  const finiteOrNull = (n: unknown) => n === null || (typeof n === "number" && Number.isFinite(n));
  if (!a.variable?.id || !a.dataset?.id || !a.dataset?.version || !a.spatial_support?.requested ||
      !Number.isFinite(a.spatial_support.requested.latitude) || !Number.isFinite(a.spatial_support.requested.longitude) ||
      !a.period?.start || !a.period?.end_exclusive || !a.units?.annual_value ||
      !Array.isArray(a.annual) || !Array.isArray(a.series) || !a.coverage ||
      !Array.isArray(a.caveats) || !Array.isArray(a.limitations) || !a.methodology) return bad();
  if (a.annual.some((y) => !Number.isInteger(y.year) || !finiteOrNull(y.value) || typeof y.eligible !== "boolean") ||
      a.series.some((m) => !/^\d{4}-\d{2}-\d{2}$/.test(m.date) || !finiteOrNull(m.value))) return bad();
  if (a.trend && (!finiteOrNull(a.trend.slope) || !Array.isArray(a.trend.eligible_years) ||
      (a.trend.confidence_interval !== null && (!Array.isArray(a.trend.confidence_interval) || a.trend.confidence_interval.length !== 2 || !a.trend.confidence_interval.every(Number.isFinite))))) return bad();
}
