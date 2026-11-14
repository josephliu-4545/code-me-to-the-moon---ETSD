import type { MethodsLab } from "./methodsLabTypes";
export type VariableId =
  | "temperature"
  | "relative_humidity"
  | "extreme_heat"
  | "precipitation"
  | "ndvi"
  | "soil_moisture";

export type Mode = "point" | "region";

export interface VariableInfo {
  id: VariableId;
  name: string;
  short_name: string;
  description: string;
  annual_value: string;
  units: string;
  slope_units: string;
  dataset: { source: string; id: string; version: string; provenance: string; doi: string | null };
  spatial_resolution: string;
  temporal_resolution: string;
  available_from: string;
  max_years: number;
  default_period: [number, number];
  modes: { point: boolean; region: boolean };
  region_unsupported_reason: string | null;
  region_shape?: string;
  default_radius_km?: number;
  max_radius_km?: number;
  default_region_span_degrees?: number;
  max_region_span_degrees?: number;
  region_description?: string;
  datasets?: string[];
  default_dataset?: string;
}

export interface VariablesResponse {
  variables: VariableInfo[];
  caveats: string[];
  api_version: string;
}

export interface Bounds {
  south: number;
  north: number;
  west: number;
  east: number;
}

export interface SpatialSupport {
  mode: Mode;
  type: string;
  description: string;
  native_grid?: string;
  resolution: string;
  radius_km?: number;
  cell?: { id?: string; center: [number, number]; bounds: Bounds; approximate: boolean };
  cell_status?: string;
  coastal_proximity?: boolean | null;
  bbox?: Bounds;
  region_area_km2?: number | null;
  min_valid_area_fraction?: number;
  months_meeting_area_threshold?: number;
  requested: { latitude: number; longitude: number };
}

export interface AnnualPoint {
  year: number;
  value: number | null;
  eligible: boolean;
  reasons: string[];
  complete_calendar_year: boolean | null;
  coverage_percentage: number | null;
  represented_months: number[] | null;
  missing_months: number[] | null;
  extra: Record<string, unknown>;
}

export interface MannKendall {
  s: number;
  tau: number;
  p_value: number;
  alpha: number;
  is_statistically_significant: boolean;
  direction: string;
  z?: number;
  variance?: number;
  alternative?: string;
}

export interface SerialDependence {
  adjacent_pair_count: number;
  lag1_spearman_rho: number | null;
  diagnostic_p_value?: number | null;
  status: string;
  caveat: string;
  supported_for_standard_inference: boolean;
  unavailable_reason: string | null;
}

export interface ChangePoint {
  status: "step_detected" | "none" | "not_tested";
  reason?: string;
  last_year_before?: number;
  first_year_after?: number;
  mean_before?: number;
  mean_after?: number;
  shift?: number;
  pettitt_p_value?: number;
  step_fits_better_than_line?: boolean;
}

export interface Trend {
  result_level: "statistical_inference" | "descriptive_slope" | "annual_summaries_only" | string;
  result_level_label: string;
  eligible_years: number[];
  excluded_years: Array<[number, string[]]> | Array<{ year: number; reasons: string[] }>;
  missing_years: number[];
  slope: number | null;
  intercept: number | null;
  slope_units: string | null;
  confidence_interval: [number, number] | null;
  confidence_interval_unavailable_reason: string | null;
  mann_kendall: MannKendall | null;
  serial_dependence: SerialDependence | null;
  slope_unavailable_reason: string | null;
  significance_unavailable_reason: string | null;
  /** Sudden-step check on the yearly values the trend used (Pettitt test + step-vs-line fit). */
  change_point?: ChangePoint;
  /** Present for NDVI: trend from monthly means compared month by month (Seasonal Kendall). */
  method?: "seasonal_kendall";
  months_used?: number[];
  sample_count?: number;
}

export interface SeriesPoint {
  date: string;
  value: number | null;
  status?: string;
  descriptive_value?: number | null;
  usable?: boolean;
}

export interface CacheInfo {
  hit: boolean;
  retrieved_at: string;
  age_seconds: number;
  shared_in_flight_request?: boolean;
}

export interface Analysis {
  variable: { id: VariableId; name: string; description: string; annual_value_definition: string };
  dataset: {
    source: string;
    id: string;
    version: string;
    provenance: string;
    doi: string | null;
    key?: string;
    title?: string;
    citation?: string;
    depth?: { top_cm: number; bottom_cm: number; semantics: string };
  };
  spatial_support: SpatialSupport;
  period: { start: string; end_exclusive: string };
  units: { annual_value: string; slope: string };
  annual: AnnualPoint[];
  series: SeriesPoint[];
  series_definition: string | null;
  trend: Trend | null;
  coverage: { years_requested: number; eligible_years: number; excluded_years: { year: number; reasons: string[] }[] };
  methodology: { source: unknown; trend_method: Record<string, string> };
  caveats: string[];
  limitations: string[];
  /** Statistical Methods Lab: OLS vs Theil–Sen and diagnostics on the same eligible observations. */
  methods_lab?: MethodsLab;
  extra: Record<string, unknown>;
  data_status: "live_nasa_retrieval" | "cached_nasa_retrieval" | "saved_snapshot";
  cache?: CacheInfo;
  snapshot?: { captured_at: string; note: string };
}

export interface AnalysisRequest {
  variable: VariableId;
  latitude: number;
  longitude: number;
  startYear: number;
  endYear: number; // exclusive
  mode: Mode;
  radiusKm?: number;
  dataset?: string;
  bbox?: [number, number, number, number];
}

export interface RelationshipsResponse {
  variables: [VariableId, VariableId];
  results: Record<string, Analysis>;
  alignment: { temporal: string; spatial: string[]; spatial_supports_differ: boolean };
  common_eligible_years: number[];
  paired_values: Array<Record<string, number>>;
  spearman_rho_annual: number | null;
  spearman_rho_first_differences: number | null;
  unavailable_reasons: string[];
  interpretation: string;
}

export interface GeocodeResult {
  name: string;
  latitude: number;
  longitude: number;
  type?: string;
}

export interface SoilMoistureComparePair {
  datasets: [string, string];
  common_valid_months: number;
  mean_difference_m3_m3: number | null;
  mean_difference_label: string;
  monthly_anomaly_spearman_rho: number | null;
  unavailable_reasons: string[];
}

export interface SoilMoistureCompare {
  datasets_are_merged: false;
  common_eligible_years: number[];
  differences: string[];
  descriptive_agreement: {
    slope_sign_agreement: boolean | null;
    pairs: SoilMoistureComparePair[];
    excluded_frozen_months: number;
  };
  results: Record<string, { trend: { theil_sen: { slope: number; slope_units: string } | null; result_level: string } }>;
  interpretation: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly reason?: string;
  readonly hasJsonBody: boolean;
  constructor(status: number, message: string, reason?: string, hasJsonBody = true) {
    super(message);
    this.status = status;
    this.reason = reason;
    this.hasJsonBody = hasJsonBody;
  }
}

/** True when the API server itself is not reachable (network error, or a proxy/static host answering instead). */
export function isUnreachable(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false;
  return err.status === 0 || (!err.hasJsonBody && (err.status === 404 || err.status >= 500));
}
