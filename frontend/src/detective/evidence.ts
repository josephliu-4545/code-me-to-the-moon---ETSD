/**
 * Layer 1 — scientific evidence.
 *
 * Extracts a structured, validated evidence object from the analysis the backend already
 * returned. Nothing here calculates a new statistic: every number is copied from the
 * authoritative API response, and anything missing stays `null` (never zero).
 */
import type { Analysis, AnalysisRequest, ChangePoint } from "../api/types";
import { dataStatusLabel, reasonLabel } from "../lib/format";
import { fittedChange, isSeasonal, monthCompleteness, periodLabel, slopeName, testName, trendVerdict, type VerdictKind } from "../lib/verdict";

const MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Identity of one investigation. Conversations are keyed by it so evidence never crosses investigations. */
export interface Investigation {
  key: string;
  variable: string;
  variableName: string;
  place: string;
  latitude: number;
  longitude: number;
  startYear: number;
  endYearInclusive: number;
  mode: string;
  dataset: string | null;
}

export interface Evidence {
  investigation: Investigation;
  variableId: string;
  variableName: string;
  annualValueDefinition: string;
  periodLabel: string;
  dataset: {
    source: string;
    id: string;
    version: string;
    provenance: string;
    title: string | null;
    citation: string | null;
    /** Only a syntactically valid DOI from the catalog; never constructed or guessed. */
    doi: string | null;
  };
  footprint: { description: string; resolution: string; mode: string; cellStatus: string | null };
  dataStatus: { kind: Analysis["data_status"]; label: string; snapshotCapturedAt: string | null };
  units: { annual: string; slope: string | null };
  observations: { eligible: { year: number; value: number }[]; excluded: { year: number; reasons: string[] }[]; missingYears: number[]; yearsRequested: number };
  monthly: { valid: number; expected: number } | null;
  /** NDVI Seasonal Kendall: the trend uses monthly values, so annual exclusions do not remove years from it. */
  seasonal: { months: string[]; sampleCount: number | null; yearsContributing: number[] } | null;
  trend: {
    verdict: VerdictKind;
    verdictLabel: string;
    verdictNote: string;
    resultLevel: string | null;
    resultLevelLabel: string | null;
    estimator: string;
    test: string;
    slope: number | null;
    slopeUnavailableReason: string | null;
    fittedChange: { value: number; from: number; to: number } | null;
    confidenceInterval: [number, number] | null;
    confidenceIntervalUnavailableReason: string | null;
    significance: { pValue: number; alpha: number; significant: boolean; tau: number } | null;
    significanceUnavailableReason: string | null;
    dependence: { status: string; rho: number | null; caveat: string; supportsInference: boolean; unavailableReason: string | null } | null;
    changePoint: ChangePoint | null;
  };
  methodsLab: {
    olsSlope: number | null;
    theilSenSlope: number | null;
    difference: number | null;
    n: number | null;
    unavailableReason: string | null;
    seasonalOls: number | null;
  } | null;
  caveats: string[];
  limitations: string[];
}

const DOI_RE = /^10\.\d{4,9}\/[^\s"<>]+$/;

/** A finite number, or null. Unavailable values are never coerced to 0. */
export function finiteOrNull(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function investigationKey(r: AnalysisRequest): string {
  return JSON.stringify([r.variable, r.latitude, r.longitude, r.startYear, r.endYear, r.mode, r.variable === "soil_moisture" ? r.dataset ?? null : null, r.mode === "region" ? r.radiusKm ?? null : null, r.bbox ?? null]);
}

export function toInvestigation(r: AnalysisRequest, variableName: string, place: string): Investigation {
  return {
    key: investigationKey(r),
    variable: r.variable,
    variableName,
    place: place.trim() || "Selected location",
    latitude: r.latitude,
    longitude: r.longitude,
    startYear: r.startYear,
    endYearInclusive: r.endYear - 1,
    mode: r.mode,
    dataset: r.variable === "soil_moisture" ? r.dataset ?? null : null,
  };
}

/** True only when the analysis really answers this investigation (guards against stale results). */
export function analysisMatches(a: Analysis, inv: Investigation): boolean {
  const req = a.spatial_support?.requested;
  const sameVariable = a.variable?.id === inv.variable;
  const samePlace = !req || (Math.abs(req.latitude - inv.latitude) < 1e-3 && Math.abs(req.longitude - inv.longitude) < 1e-3);
  const samePeriod = a.period?.start?.slice(0, 4) === String(inv.startYear);
  const sameDataset = inv.dataset === null || !a.dataset.key || a.dataset.key === inv.dataset;
  return sameVariable && samePlace && samePeriod && sameDataset;
}

function exclusions(a: Analysis): { year: number; reasons: string[] }[] {
  const fromCoverage = a.coverage?.excluded_years ?? [];
  if (fromCoverage.length) return fromCoverage.map((e) => ({ year: e.year, reasons: (e.reasons ?? []).map(reasonLabel) }));
  return a.annual.filter((y) => !y.eligible).map((y) => ({ year: y.year, reasons: y.reasons.map(reasonLabel) }));
}

export function buildEvidence(a: Analysis, inv: Investigation): Evidence {
  const t = a.trend;
  const v = trendVerdict(a);
  const mk = t?.mann_kendall;
  const sd = t?.serial_dependence;
  const ci = t?.confidence_interval;
  const validCi = ci && finiteOrNull(ci[0]) !== null && finiteOrNull(ci[1]) !== null ? ([ci[0], ci[1]] as [number, number]) : null;
  const completeness = monthCompleteness(a);
  const lab = a.methods_lab;
  const labAnnual = lab && !lab.applicable?.seasonal ? lab : null;
  const doi = typeof a.dataset.doi === "string" && DOI_RE.test(a.dataset.doi.trim()) ? a.dataset.doi.trim() : null;
  const status = dataStatusLabel(a);
  return {
    investigation: inv,
    variableId: a.variable.id,
    variableName: a.variable.name,
    annualValueDefinition: a.variable.annual_value_definition,
    periodLabel: periodLabel(a),
    dataset: {
      source: a.dataset.source,
      id: a.dataset.id,
      version: a.dataset.version,
      provenance: a.dataset.provenance,
      title: a.dataset.title ?? null,
      citation: a.dataset.citation ?? null,
      doi,
    },
    footprint: {
      description: a.spatial_support.description,
      resolution: a.spatial_support.resolution,
      mode: a.spatial_support.mode,
      cellStatus: a.spatial_support.cell_status ?? null,
    },
    dataStatus: { kind: a.data_status, label: status.label, snapshotCapturedAt: a.data_status === "saved_snapshot" ? a.snapshot?.captured_at ?? null : null },
    units: { annual: a.units.annual_value, slope: t?.slope_units ?? a.units.slope ?? null },
    observations: {
      eligible: a.annual.filter((y) => y.eligible && finiteOrNull(y.value) !== null).map((y) => ({ year: y.year, value: y.value as number })),
      excluded: exclusions(a),
      missingYears: t?.missing_years ?? [],
      yearsRequested: a.coverage?.years_requested ?? a.annual.length,
    },
    monthly: completeness.expected > 0 ? completeness : null,
    seasonal: isSeasonal(a) ? { months: (t?.months_used ?? []).map((m) => MONTH_ABBR[m - 1] ?? String(m)), sampleCount: finiteOrNull(t?.sample_count), yearsContributing: t?.eligible_years ?? [] } : null,
    trend: {
      verdict: v.kind,
      verdictLabel: v.label,
      verdictNote: v.note,
      resultLevel: t?.result_level ?? null,
      resultLevelLabel: t?.result_level_label ?? null,
      estimator: slopeName(a),
      test: testName(a),
      slope: finiteOrNull(t?.slope),
      slopeUnavailableReason: t?.slope_unavailable_reason ?? (t ? null : "No trend result was returned for this analysis."),
      fittedChange: fittedChange(a),
      confidenceInterval: validCi,
      confidenceIntervalUnavailableReason: validCi ? null : t?.confidence_interval_unavailable_reason ?? null,
      significance:
        mk && t?.result_level === "statistical_inference" && finiteOrNull(mk.p_value) !== null
          ? { pValue: mk.p_value, alpha: mk.alpha, significant: mk.is_statistically_significant, tau: mk.tau }
          : null,
      significanceUnavailableReason: t?.significance_unavailable_reason ?? null,
      dependence: sd
        ? { status: sd.status, rho: finiteOrNull(sd.lag1_spearman_rho), caveat: sd.caveat, supportsInference: sd.supported_for_standard_inference, unavailableReason: sd.unavailable_reason }
        : null,
      changePoint: t?.change_point ?? null,
    },
    methodsLab: lab
      ? {
          olsSlope: finiteOrNull(labAnnual?.ols?.slope),
          theilSenSlope: finiteOrNull(labAnnual?.theil_sen?.slope),
          difference: finiteOrNull(labAnnual?.comparison?.slope_difference),
          n: finiteOrNull(labAnnual?.comparison?.n),
          unavailableReason: labAnnual ? labAnnual.comparison_unavailable_reason ?? labAnnual.ols?.unavailable_reason ?? null : lab.annual_comparison_unavailable_reason ?? null,
          seasonalOls: finiteOrNull(lab.seasonal?.deseasonalized_ols_slope),
        }
      : null,
    caveats: a.caveats ?? [],
    limitations: a.limitations ?? [],
  };
}
