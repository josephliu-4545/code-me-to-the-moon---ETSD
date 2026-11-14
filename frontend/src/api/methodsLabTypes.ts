import type { ChangePoint, MannKendall, SerialDependence } from "./types";

export interface LabObservation {
  year: number;
  value: number | null;
  reasons?: string[];
}

export interface LabFittedPoint {
  year: number;
  observed: number;
  ols: number;
  theil_sen: number;
}

export interface MethodInfo {
  name: string;
  definition: string;
  role: string;
}

export interface MethodsLab {
  applicable: { annual_comparison: boolean; seasonal: boolean };
  requirements: { minimum_years_for_slope: number; minimum_years_for_significance: number; alpha: number; dependence_screen: string };
  mann_kendall: MannKendall | null;
  significance_unavailable_reason: string | null;
  serial_dependence: SerialDependence | null;
  change_point?: ChangePoint | null;
  methods: Record<string, MethodInfo>;
  observations: { basis: string; eligible: LabObservation[]; excluded: LabObservation[] };
  unavailable?: string;
  ols?: {
    available: boolean;
    n: number;
    slope: number | null;
    intercept: number | null;
    r_squared: number | null;
    r_squared_unavailable_reason: string | null;
    residuals: { year: number; residual: number }[];
    unavailable_reason: string | null;
    slope_units: string | null;
    inference: null;
    inference_note: string;
  };
  theil_sen?: {
    available: boolean;
    n: number;
    slope: number | null;
    intercept: number | null;
    slope_units: string | null;
    confidence_interval: [number, number] | null;
    confidence_interval_unavailable_reason: string | null;
    unavailable_reason: string | null;
    source: string;
  };
  comparison?: {
    same_observations: boolean;
    n: number;
    slope_difference: number;
    slope_units: string | null;
    fitted: LabFittedPoint[];
    fit_range: [number, number];
    note: string;
  } | null;
  comparison_unavailable_reason?: string;
  annual_comparison_unavailable_reason?: string;
  seasonal: {
    method: "seasonal_kendall";
    months_used: number[];
    months_not_used: number[];
    month_names_used: string[];
    years_contributing: number[];
    sample_count: number;
    seasonal_sen_slope: number | null;
    slope_units: string | null;
    confidence_interval: [number, number] | null;
    confidence_interval_unavailable_reason: string | null;
    seasonal_kendall: MannKendall | null;
    deseasonalized_ols_slope: number | null;
    deseasonalized_ols_unavailable_reason: string | null;
    comparison_note: string;
    availability_rule: string;
  } | null;
  seasonal_unavailable_reason?: string;
}
