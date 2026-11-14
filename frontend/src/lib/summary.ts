import type { Analysis } from "../api/types";
import { fmt, signed } from "./format";

/**
 * Plain-language summary built only from values the backend returned.
 * It never adds conclusions the statistics do not support.
 */
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
  lines.push(
    `Across ${t.eligible_years.length} eligible years (${first}–${last}), annual ${name} changed at a median rate of ` +
      `${signed(t.slope, 4)} ${t.slope_units} (Theil–Sen), about ${signed(t.slope * 10, 3)} per decade.`,
  );
  if (t.result_level === "statistical_inference" && t.mann_kendall) {
    const mk = t.mann_kendall;
    lines.push(
      mk.is_statistically_significant
        ? `The Mann–Kendall test rejects "no monotonic trend" at α = ${mk.alpha} (p = ${fmt(mk.p_value, 3)}). Treat this as indicative: the screened test can give false positives more often than 5% when years are autocorrelated.`
        : `The Mann–Kendall test does not detect a monotonic trend at α = ${mk.alpha} (p = ${fmt(mk.p_value, 3)}). The data are consistent with no trend; this is not proof of no change.`,
    );
    if (t.confidence_interval) {
      lines.push(`95% interval for the slope: ${signed(t.confidence_interval[0], 4)} to ${signed(t.confidence_interval[1], 4)} ${t.slope_units}.`);
    }
  } else {
    lines.push(`No significance test is reported${t.significance_unavailable_reason ? `: ${t.significance_unavailable_reason.replace(/\.$/, "")}` : ""}. The slope is descriptive only.`);
  }
  if (total > eligible.length) {
    lines.push(`${total - eligible.length} year(s) were excluded from the trend; see Scientific Evaluation for reasons.`);
  }
  return lines;
}
