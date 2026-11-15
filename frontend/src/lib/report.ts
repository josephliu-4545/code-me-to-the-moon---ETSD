import type { Analysis, AnalysisRequest } from "../api/types";
import { trendVerdict } from "./verdict";

export interface MissionReportData {
  schema: "earth-system-trend-detective/mission-report/v1";
  generated_at: string;
  investigation: {
    id: string | null;
    place: string;
    request: AnalysisRequest;
    period: Analysis["period"];
    variable: Analysis["variable"];
    dataset: Analysis["dataset"];
    spatial_support: Analysis["spatial_support"];
  };
  finding: {
    verdict: ReturnType<typeof trendVerdict>;
    trend: Analysis["trend"];
    coverage: Analysis["coverage"];
    units: Analysis["units"];
  };
  evidence: { annual: Analysis["annual"]; series: Analysis["series"] };
  scientific_context: { methodology: Analysis["methodology"]; caveats: string[]; limitations: string[] };
  provenance: { data_status: Analysis["data_status"]; cache?: Analysis["cache"]; snapshot?: Analysis["snapshot"]; retrieved_at: string | null };
}

export function buildMissionReport(analysis: Analysis, request: AnalysisRequest, place: string, now = new Date()): MissionReportData {
  return {
    schema: "earth-system-trend-detective/mission-report/v1",
    generated_at: now.toISOString(),
    investigation: {
      id: analysis.investigation?.id ?? null,
      place,
      request,
      period: analysis.period,
      variable: analysis.variable,
      dataset: analysis.dataset,
      spatial_support: analysis.spatial_support,
    },
    finding: { verdict: trendVerdict(analysis), trend: analysis.trend, coverage: analysis.coverage, units: analysis.units },
    evidence: { annual: analysis.annual, series: analysis.series },
    scientific_context: { methodology: analysis.methodology, caveats: analysis.caveats, limitations: analysis.limitations },
    provenance: {
      data_status: analysis.data_status,
      cache: analysis.cache,
      snapshot: analysis.snapshot,
      retrieved_at: analysis.investigation?.retrieved_at ?? analysis.cache?.retrieved_at ?? null,
    },
  };
}

export function settingsUrl(request: AnalysisRequest, place: string, origin = window.location.origin, pathname = window.location.pathname): string {
  const params = new URLSearchParams({
    lat: request.latitude.toFixed(4), lon: request.longitude.toFixed(4), place,
    v: request.variable, from: String(request.startYear), to: String(request.endYear - 1), mode: request.mode,
  });
  if (request.radiusKm !== undefined) params.set("r", String(request.radiusKm));
  if (request.dataset) params.set("ds", request.dataset);
  if (request.bbox) params.set("bbox", request.bbox.join(","));
  return `${origin}${pathname}?${params.toString()}#explore`;
}
