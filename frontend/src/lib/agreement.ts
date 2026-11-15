/**
 * Plain-language labels for dataset agreement. Directions come from slopes over the common
 * eligible years of each pair (matched observations). They are descriptive unless both datasets'
 * own significance tests cover exactly those years, so a pair of opposite signs is never called a
 * conflict, and agreement is never presented as proof of accuracy.
 */
import type { DirectionEvidence, PairComparison } from "../api/compareTypes";

/** Used when an older backend response has no `label`; identifiers are unchanged for compatibility. */
const FALLBACK_LABELS: Record<string, string> = {
  consistent: "Same descriptive direction, strong co-variation",
  same_direction_weak_covariation: "Same descriptive direction, weak co-variation",
  same_direction_covariation_not_assessable: "Same descriptive direction; co-variation not assessable",
  conflicting_trend_direction: "Opposite descriptive slope directions",
  mixed: "Mixed descriptive directions",
  partially_assessable: "Partially assessable: some dataset pairs could not be compared",
  not_assessable: "Not assessable",
};

export function agreementLabel(agreement: { level: string; label?: string }): string {
  return agreement.label ?? FALLBACK_LABELS[agreement.level] ?? "Not assessable";
}

const DIRECTION_LABELS: Record<DirectionEvidence, string> = {
  descriptive_same_direction: "Same (descriptive)",
  descriptive_opposite_direction: "Opposite (descriptive)",
  indicative_same_direction: "Same (indicative)",
  indicative_opposite_direction: "Opposite (indicative)",
  descriptive_no_direction: "No direction (a slope is exactly zero)",
  unavailable: "Not assessable (fewer than 3 common years)",
};

/** Pair direction over common eligible years; never the full-request sign. */
export function pairDirection(p: Pick<PairComparison, "direction_evidence" | "common_period_slope_sign_agreement">): DirectionEvidence {
  if (p.direction_evidence) return p.direction_evidence;
  const agree = p.common_period_slope_sign_agreement;
  return agree == null ? "unavailable" : agree ? "descriptive_same_direction" : "descriptive_opposite_direction";
}

export function directionLabel(p: Pick<PairComparison, "direction_evidence" | "common_period_slope_sign_agreement">): string {
  return DIRECTION_LABELS[pairDirection(p)];
}
