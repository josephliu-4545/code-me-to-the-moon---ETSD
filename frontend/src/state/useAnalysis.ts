import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { isUnreachable, type Analysis, type AnalysisRequest, type VariablesResponse } from "../api/types";

export const analysisKey = (r: AnalysisRequest | null) => ["analysis", r] as const;

export function useAnalysis(request: AnalysisRequest | null) {
  return useQuery({
    queryKey: analysisKey(request),
    queryFn: ({ signal }) => api.analysis(request!, signal),
    enabled: request !== null,
  });
}

export type VariablesResult = VariablesResponse & { offline?: boolean };

/** Variables catalog; falls back to a saved copy (offline mode) only if the backend is unreachable. */
export function useVariables() {
  return useQuery<VariablesResult>({
    queryKey: ["variables"],
    staleTime: Infinity,
    queryFn: async ({ signal }) => {
      try {
        return await api.variables(signal);
      } catch (err) {
        if (!isUnreachable(err)) throw err;
        const saved = await fetch(`${import.meta.env.BASE_URL}snapshots/variables.json`);
        if (!saved.ok) throw err;
        return { ...((await saved.json()) as VariablesResponse), offline: true };
      }
    },
  });
}

interface SnapshotIndexEntry {
  variable: string;
  latitude: number;
  longitude: number;
  startYear: number;
  endYear: number;
  dataset?: string;
  mode: string;
  file: string;
}

/** Saved snapshots of earlier live retrievals, used only when the backend is unreachable. */
export async function findSnapshot(r: AnalysisRequest): Promise<Analysis | null> {
  try {
    const index = (await (await fetch(`${import.meta.env.BASE_URL}snapshots/index.json`)).json()) as {
      captured_at: string;
      note: string;
      entries: SnapshotIndexEntry[];
    };
    const hit = index.entries.find(
      (e) =>
        e.variable === r.variable &&
        Math.abs(e.latitude - r.latitude) < 1e-3 &&
        Math.abs(e.longitude - r.longitude) < 1e-3 &&
        e.startYear === r.startYear &&
        e.endYear === r.endYear &&
        e.mode === r.mode &&
        (r.variable !== "soil_moisture" || e.dataset === r.dataset),
    );
    if (!hit) return null;
    const body = (await (await fetch(`${import.meta.env.BASE_URL}snapshots/${hit.file}`)).json()) as Analysis;
    return { ...body, data_status: "saved_snapshot", cache: undefined, snapshot: { captured_at: index.captured_at, note: index.note } };
  } catch {
    return null;
  }
}
