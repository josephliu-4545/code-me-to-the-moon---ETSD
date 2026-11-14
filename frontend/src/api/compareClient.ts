import { getJson } from "./client";
import type { CompareResponse, DatasetsResponse } from "./compareTypes";

export interface CompareRequest {
  variable: string;
  datasets: string[];
  latitude: number;
  longitude: number;
  startYear: number;
  endYear: number; // exclusive
}

export const compareApi = {
  datasets: (signal?: AbortSignal) => getJson<DatasetsResponse>("/api/v2/datasets", {}, signal),
  compare: (r: CompareRequest, signal?: AbortSignal) =>
    getJson<CompareResponse>(
      "/api/v2/compare",
      {
        variable: r.variable,
        datasets: r.datasets.join(","),
        latitude: r.latitude,
        longitude: r.longitude,
        start_date: `${r.startYear}-01-01`,
        end_date: `${r.endYear}-01-01`,
      },
      signal,
    ),
};
