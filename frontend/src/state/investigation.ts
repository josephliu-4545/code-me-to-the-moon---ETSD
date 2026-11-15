/**
 * The executed investigation, kept for this browser tab only.
 *
 * The URL stores the *selection* (place, variable, period) so it can be shared. Opening a shared URL
 * never runs an analysis. After a reload in the same tab, the last *executed* investigation is
 * remembered here so the app can offer an explicit "Resume investigation" action instead of
 * silently repeating NASA / Earth Engine requests.
 */
import type { AnalysisRequest, VariableId } from "../api/types";

export const LAST_INVESTIGATION_KEY = "estd-last-investigation";
const VARIABLES: VariableId[] = ["temperature", "relative_humidity", "extreme_heat", "precipitation", "ndvi", "soil_moisture"];

export interface StoredInvestigation {
  request: AnalysisRequest;
  place: string;
}

const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Accept only a well-formed request; anything else is ignored rather than guessed. */
export function parseStoredInvestigation(raw: string | null): StoredInvestigation | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as { request?: Record<string, unknown>; place?: unknown };
    const r = value.request;
    if (!r || !VARIABLES.includes(r.variable as VariableId)) return null;
    if (!finite(r.latitude) || !finite(r.longitude) || Math.abs(r.latitude) > 90 || Math.abs(r.longitude) > 180) return null;
    if (!Number.isInteger(r.startYear) || !Number.isInteger(r.endYear) || (r.endYear as number) <= (r.startYear as number)) return null;
    if (r.mode !== "point" && r.mode !== "region") return null;
    if (r.radiusKm !== undefined && !finite(r.radiusKm)) return null;
    if (r.dataset !== undefined && typeof r.dataset !== "string") return null;
    if (r.bbox !== undefined && !(Array.isArray(r.bbox) && r.bbox.length === 4 && r.bbox.every(finite))) return null;
    return { request: r as unknown as AnalysisRequest, place: typeof value.place === "string" ? value.place.slice(0, 200) : "" };
  } catch {
    return null;
  }
}

export function readStoredInvestigation(): StoredInvestigation | null {
  try {
    return parseStoredInvestigation(window.sessionStorage.getItem(LAST_INVESTIGATION_KEY));
  } catch {
    return null; // storage blocked: resuming is simply not offered
  }
}

export function storeInvestigation(value: StoredInvestigation | null): void {
  try {
    if (value) window.sessionStorage.setItem(LAST_INVESTIGATION_KEY, JSON.stringify(value));
    else window.sessionStorage.removeItem(LAST_INVESTIGATION_KEY);
  } catch {
    /* not remembered; nothing else depends on it */
  }
}
