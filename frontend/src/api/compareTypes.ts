import type { Analysis } from "./types";

export interface DatasetInfo {
  key: string;
  variable: string;
  name: string;
  provider: string;
  collection_id: string;
  version: string;
  measurement: string;
  product_type: string;
  native_units: string;
  units: string;
  slope_units: string;
  temporal_resolution: string;
  spatial_resolution: string;
  available_from: string;
  available_to: string | null;
  coverage_note: string;
  quality_control: string;
  processing: string;
  lineage: string;
  shared_inputs: string[];
  limitations: string[];
  citation: string;
  doi: string | null;
  license: string;
  comparable_quantity: string;
  is_primary: boolean;
  modes: string[];
  max_years: number;
  latitude_limits: [number, number];
  supports_region: boolean;
}

export interface VariableDatasets {
  variable: string;
  datasets: DatasetInfo[];
  comparison_available: boolean;
  not_yet_available_reason: string | null;
  relationships: { datasets: [string, string]; lineage: string; note: string; numerically_comparable: boolean }[];
}

export interface DatasetsResponse {
  variables: VariableDatasets[];
  outcomes: Record<string, string>;
}

export type Outcome =
  | "inference"
  | "descriptive_only"
  | "insufficient_coverage"
  | "no_data"
  | "unsupported_location"
  | "unsupported_mode"
  | "outside_record"
  | "provider_error";

export interface DatasetResult {
  entry: DatasetInfo;
  outcome: Outcome;
  message: string;
  http_status?: number;
  analysis: Analysis | null;
}

export interface PairComparison {
  datasets: [string, string];
  lineage: "same_lineage" | "partially_related" | "independent";
  lineage_note: string;
  numerically_comparable: boolean;
  not_comparable_reason?: string;
  common_eligible_years: number[];
  full_period_slopes: Record<string, number | null>;
  common_period_slopes: Record<string, number> | null;
  common_period_slope_sign_agreement?: boolean | null;
  slope_sign_agreement: boolean | null;
  confidence_intervals_overlap: boolean | null;
  annual_differences: { year: number; difference: number }[] | null;
  mean_difference: number | null;
  mean_absolute_difference: number | null;
  root_mean_square_difference?: number | null;
  slope_difference?: number | null;
  difference_units?: string;
  difference_label?: string;
  spearman_rho: number | null;
  pearson_r: number | null;
  spearman_rho_year_to_year: number | null;
  unavailable_reasons: string[];
  matched_observations?: MatchedObservations;
  metrics?: EvaluationMetric[];
}

export type CoverageStatus = "valid" | "missing" | "excluded" | "provisional" | "outside_coverage" | "unavailable";

export interface CoverageCell {
  period: string;
  status: CoverageStatus;
  reasons: string[];
  value: number | null;
}

export interface DatasetEvaluation {
  dataset: string;
  resolution: "monthly" | "annual";
  resolution_note: string;
  requested_period: { start: string; end_exclusive: string };
  supported_period: { start: string; end: string | null };
  cells: CoverageCell[];
  counts: Record<CoverageStatus, number>;
  completeness: {
    valid: number;
    expected_within_supported_coverage: number;
    percentage: number | null;
    label: string;
    status?: "observed" | "unavailable";
    unavailable_reason?: string | null;
  };
  eligible_years: number[];
  excluded_years: { year: number; reasons: string[] }[];
}

export interface MatchedObservations {
  resolution: "annual";
  count: number;
  period: { start: string; end: string } | null;
  labels: string[];
  valid_observations: Record<string, string[]>;
  excluded_from_pairing: Record<string, string[]>;
  quality_excluded: Record<string, string[]>;
}

export interface EvaluationMetric {
  id: string;
  name: string;
  value: number | boolean | null;
  units: string | null;
  matched_observations: number;
  definition: string;
  interpretation: string;
  limitations: string;
  availability: "available" | "unavailable";
  unavailable_reason: string | null;
}

export interface EvaluationEvidence {
  datasets: Record<string, DatasetEvaluation>;
  pairs: PairComparison[];
  cautions: string[];
}

export interface CompareResponse {
  variable: string;
  location: { latitude: number; longitude: number; mode: string };
  period: { start: string; end_exclusive: string };
  datasets_requested: string[];
  datasets_are_merged: false;
  results: Record<string, DatasetResult>;
  succeeded: string[];
  comparison: {
    pairs: PairComparison[];
    all_numerically_comparable: boolean;
    common_eligible_years_all: number[];
    agreement: { level: string; slope_sign_agreement_all: boolean | null; min_spearman_rho: number | null; explanation: string; caution: string };
    method: Record<string, string>;
  } | null;
  comparison_unavailable_reason: string | null;
  caveats: string[];
  evaluation?: EvaluationEvidence;
}
