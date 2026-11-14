import type { Analysis } from "../api/types";

const MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * NDVI trends come from monthly means compared month by month (Seasonal Kendall), because
 * cloud gaps leave too few complete years for the annual method used by other variables.
 */
export const isSeasonal = (a: Analysis): boolean => a.trend?.method === "seasonal_kendall";
export const testName = (a: Analysis): string => (isSeasonal(a) ? "Seasonal Kendall" : "Mann–Kendall");
export const slopeName = (a: Analysis): string => (isSeasonal(a) ? "Seasonal Sen slope" : "Theil–Sen slope");
/** Calendar months the seasonal trend used, e.g. "Jan, Feb, Nov, Dec". */
export const monthsUsed = (a: Analysis): string => (a.trend?.months_used ?? []).map((m) => MONTH_ABBR[m - 1]).join(", ");

/**
 * Translates the backend's trend result into a cautious headline.
 * It never upgrades a result: a non-significant test is "no trend detected"
 * (not "unchanged"), and missing inference is "trend unavailable" (not "no trend").
 */
export type VerdictKind = "increasing" | "decreasing" | "not_detected" | "descriptive" | "unavailable";

export interface Verdict {
  kind: VerdictKind;
  /** Short headline label. */
  label: string;
  /** Value for the inference evidence cell. */
  inference: string;
  /** One-line qualification shown under the headline. */
  note: string;
}

export function trendVerdict(a: Analysis): Verdict {
  const t = a.trend;
  if (a.spatial_support.cell_status === "no_valid_land_values" || !t || t.result_level === "annual_summaries_only" || t.slope === null) {
    return {
      kind: "unavailable",
      label: "Trend unavailable",
      inference: "Trend unavailable",
      note: isSeasonal(a)
        ? "Too few calendar months have data in enough years to estimate a slope. Monthly and annual values are shown descriptively."
        : "Too few eligible years (or no valid values) to estimate a slope. Annual values are shown descriptively where they exist.",
    };
  }
  if (t.result_level === "statistical_inference" && t.mann_kendall) {
    if (t.mann_kendall.is_statistically_significant) {
      const up = t.slope > 0;
      return {
        kind: up ? "increasing" : "decreasing",
        label: up ? "Indicative increase" : "Indicative decrease",
        inference: "Significant*",
        note: isSeasonal(a)
          ? "Seasonal Kendall rejects “no monotonic trend”. Indicative only: correlation between neighbouring months is not corrected for, so the p-value may be too small."
          : "Mann–Kendall rejects “no monotonic trend”. Indicative only: autocorrelated years can inflate false positives.",
      };
    }
    return {
      kind: "not_detected",
      label: "No trend detected",
      inference: "Not significant",
      note: "The test did not detect a monotonic trend. This is consistent with no trend, but it is not proof of no change.",
    };
  }
  return {
    kind: "descriptive",
    label: "Descriptive slope only",
    inference: "Descriptive",
    note: "A slope was estimated but no significance test is reported, so its direction is descriptive only.",
  };
}

/** Months with valid data versus months expected, across years that report monthly representation. */
export function monthCompleteness(a: Analysis): { valid: number; expected: number } {
  const reporting = a.annual.filter((y) => y.represented_months !== null);
  return {
    valid: reporting.reduce((n, y) => n + (y.represented_months?.length ?? 0), 0),
    expected: reporting.length * 12,
  };
}

export function periodLabel(a: Analysis): string {
  const start = a.period.start?.slice(0, 4);
  const end = Number(a.period.end_exclusive?.slice(0, 4)) - 1;
  return `${start}–${Number.isFinite(end) ? end : "?"}`;
}

/** Lower-cases a variable name for use mid-sentence without breaking acronyms ("NDVI"). */
export function inSentence(name: string): string {
  return /^[A-Z][a-z]/.test(name) ? name[0]!.toLowerCase() + name.slice(1) : name;
}

/**
 * Discovery headline built strictly from the returned statistics.
 * Direction words for non-significant or descriptive results describe the slope only,
 * and always carry their qualification.
 */
export function discoveryHeadline(a: Analysis): string {
  const v = trendVerdict(a);
  const name = inSentence(a.variable.name);
  const slope = a.trend?.slope ?? 0;
  const dir = slope > 0 ? "An upward" : slope < 0 ? "A downward" : null;
  switch (v.kind) {
    case "unavailable":
      return "There isn’t enough reliable data to determine a long-term trend.";
    case "increasing":
      return `An upward signal in ${name}, indicated by the trend test.`;
    case "decreasing":
      return `A downward signal in ${name}, indicated by the trend test.`;
    case "not_detected":
      return dir ? `${dir} slope in ${name}, but the evidence is inconclusive.` : `No monotonic trend detected in ${name}.`;
    case "descriptive":
      return dir ? `${dir} slope in ${name}, described without a significance test.` : `A flat slope in ${name}, described without a significance test.`;
  }
}

/**
 * Change implied by the fitted Theil–Sen line between the first and last eligible
 * years. This is a property of the fitted line, not the observed start-to-end difference.
 */
export function fittedChange(a: Analysis): { value: number; from: number; to: number } | null {
  const t = a.trend;
  if (!t || t.slope === null || t.eligible_years.length < 2) return null;
  const from = Math.min(...t.eligible_years);
  const to = Math.max(...t.eligible_years);
  return to > from ? { value: t.slope * (to - from), from, to } : null;
}

/** Plain-language reading of the slope interval. */
export function intervalReading(a: Analysis): string | null {
  const t = a.trend;
  if (!t?.confidence_interval || t.slope === null) return null;
  const [lo, hi] = t.confidence_interval;
  if (lo <= 0 && hi >= 0) return "The interval includes zero, so the data are also consistent with no change over this period.";
  return `The interval excludes zero: within it, the slope is consistently ${lo > 0 ? "positive" : "negative"}. It still depends on the caveats below.`;
}
