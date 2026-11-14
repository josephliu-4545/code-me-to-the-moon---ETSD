import type { Analysis } from "../api/types";
import { pText, signed } from "./format";

/**
 * Plain-language summary built only from values the backend returned.
 * It never adds conclusions the statistics do not support.
 */
/** Warning when the yearly values jump once and stay at the new level (often a data change). */
export function stepWarning(a: Analysis): string | null {
  const cp = a.trend?.change_point;
  if (cp?.status !== "step_detected" || cp.shift === undefined) return null;
  return (
    `Values shift suddenly between ${cp.last_year_before} and ${cp.first_year_after} (${signed(cp.shift, 3)} ${a.units.annual_value}) and stay at the new level. ` +
    "The trend may come from this step, for example a change in the data source, rather than gradual change."
  );
}

const monthName = (m: number) => ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m - 1];

export function summarize(a: Analysis): string[] {
  const lines: string[] = [];
  const t = a.trend;
  const eligible = a.annual.filter((y) => y.eligible && y.value !== null);
  const total = a.annual.length;
  const name = a.variable.name.toLowerCase();

  if (a.spatial_support.cell_status === "no_valid_land_values") {
    lines.push("No valid values were available for the grid cell at this location, so no trend can be estimated. No neighbouring cell was substituted.");
    return lines;
  }
  const seasonal = t?.method === "seasonal_kendall";
  const test = seasonal ? "Seasonal Kendall test" : "Mann–Kendall test";
  if (seasonal && (t.result_level === "annual_summaries_only" || t.slope === null)) {
    lines.push(`No trend can be estimated: ${(t.slope_unavailable_reason ?? "too few monthly values").replace(/.$/, "").toLowerCase()}.`);
    lines.push("Monthly and annual values are still shown descriptively.");
    return lines;
  }
  if (!t || t.result_level === "annual_summaries_only" || t.slope === null) {
    lines.push(
      `Only ${eligible.length} of ${total} years met the data-completeness rules, which is not enough to estimate a trend` +
        (t?.slope_unavailable_reason ? ` (${t.slope_unavailable_reason.toLowerCase()}).` : "."),
    );
    if (eligible.length) lines.push("Annual values are still shown descriptively.");
    return lines;
  }
  const first = Math.min(...t.eligible_years);
  const last = Math.max(...t.eligible_years);
  if (seasonal) {
    const months = (t.months_used ?? []).map(monthName).join(", ");
    lines.push(
      `Comparing each month only with the same month in other years (${t.sample_count} monthly values from ${months}, ${first}–${last}), ` +
        `${name} changed at a median rate of ${signed(t.slope, 4)} ${t.slope_units}, about ${signed(t.slope * 10, 3)} per decade.`,
    );
    lines.push("Cloud or data gaps leave too few complete years for an annual trend, so this uses the monthly values instead.");
  } else lines.push(
    `Across ${t.eligible_years.length} eligible years (${first}–${last}), annual ${name} changed at a median rate of ` +
      `${signed(t.slope, 4)} ${t.slope_units} (Theil–Sen), about ${signed(t.slope * 10, 3)} per decade.`,
  );
  if (t.result_level === "statistical_inference" && t.mann_kendall) {
    const mk = t.mann_kendall;
    lines.push(
      mk.is_statistically_significant
        ? `The ${test} rejects "no monotonic trend" at α = ${mk.alpha} (${pText(mk.p_value)}). Treat this as indicative: ${seasonal ? "correlation between neighbouring months is not corrected for, so the p-value may be too small." : "the screened test can give false positives more often than 5% when years are autocorrelated."}`
        : `The ${test} does not detect a monotonic trend at α = ${mk.alpha} (${pText(mk.p_value)}). The data are consistent with no trend; this is not proof of no change.`,
    );
    if (t.confidence_interval) {
      lines.push(`95% interval for the slope: ${signed(t.confidence_interval[0], 4)} to ${signed(t.confidence_interval[1], 4)} ${t.slope_units}.`);
    }
  } else {
    lines.push(`No significance test is reported${t.significance_unavailable_reason ? `: ${t.significance_unavailable_reason.replace(/\.$/, "")}` : ""}. The slope is descriptive only.`);
  }
  if (!seasonal && total > eligible.length) {
    lines.push(`${total - eligible.length} year(s) were excluded from the trend; see Scientific Evaluation for reasons.`);
  }
  return lines;
}
