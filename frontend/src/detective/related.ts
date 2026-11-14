/**
 * Layer 3 support — related evidence the user has ALREADY produced elsewhere in the app.
 *
 * Compare Datasets and Earth System Relationships results are read from the TanStack Query
 * cache only when they match the active investigation's location and period. Nothing here
 * starts a retrieval: if the evidence is not in the cache, the assistant says which analysis to run.
 */
import type { CompareRequest } from "../api/compareClient";
import type { CompareResponse, DirectionEvidence } from "../api/compareTypes";
import { agreementLabel, pairDirection } from "../lib/agreement";
import type { RelationshipsResponse } from "../api/types";
import { finiteOrNull, spatialMatches, type Investigation } from "./evidence";

export interface ComparisonEvidence {
  variable: string;
  datasets: { key: string; name: string; outcome: string; message: string; version: string; citation: string | null }[];
  /** Backend level identifier (kept for reference; never shown raw). */
  agreementLevel: string | null;
  /** Plain-language, descriptive-or-indicative label for the level. */
  agreementLabel: string | null;
  directionEvidence: "descriptive" | "indicative" | "unavailable" | null;
  /** Whether the headline covers every pair, only some pairs, or none. */
  directionCoverage: "complete" | "partial" | "none" | null;
  pairsTotal: number | null;
  pairsWithDirection: number | null;
  independenceNote: string | null;
  comparabilityNote: string | null;
  explanation: string | null;
  caution: string | null;
  unavailableReason: string | null;
  pairs: {
    names: [string, string];
    lineage: string;
    lineageNote: string;
    numericallyComparable: boolean;
    notComparableReason: string | null;
    /** Direction over the pair's common eligible years (never the full-request sign). */
    direction: DirectionEvidence;
    spearmanRho: number | null;
    commonYears: number;
    unavailableReasons: string[];
  }[];
  caveats: string[];
}

export interface RelationshipEvidence {
  other: string;
  rhoAnnual: number | null;
  rhoFirstDifferences: number | null;
  commonYears: number[];
  interpretation: string;
  unavailableReasons: string[];
  spatialSupportsDiffer: boolean;
}

export interface RelatedEvidence {
  comparison: ComparisonEvidence | null;
  relationships: RelationshipEvidence[];
}

type RelKey = { a: string; b: string; lat: number; lon: number; from: number; to: number; ds: string };

const near = (x: number, y: number) => Math.abs(x - y) < 1e-3;

/**
 * A comparison is reusable only for the same kind of footprint: a point comparison is not evidence
 * about a region (and vice versa), and a regional comparison must cover the same region.
 */
function comparisonSpatiallyCompatible(res: CompareResponse, inv: Investigation): boolean {
  if ((res.location?.mode ?? "point") !== inv.mode) return false;
  const supports = Object.values(res.results ?? {}).flatMap((r) => (r.analysis ? [r.analysis.spatial_support] : []));
  return inv.mode === "point" ? supports.every((ss) => ss.mode === "point") : supports.length > 0 && supports.every((ss) => spatialMatches(ss, inv));
}

export function comparisonFromCache(entries: [readonly unknown[], unknown][], inv: Investigation): ComparisonEvidence | null {
  for (const [key, data] of entries) {
    const req = key[1] as CompareRequest | null | undefined;
    const res = data as CompareResponse | undefined;
    if (!req || !res || req.variable !== inv.variable) continue;
    if (!near(req.latitude, inv.latitude) || !near(req.longitude, inv.longitude)) continue;
    if (req.startYear !== inv.startYear || req.endYear !== inv.endYearInclusive + 1) continue;
    if (!comparisonSpatiallyCompatible(res, inv)) continue;
    const name = (k: string) => res.results[k]?.entry.name ?? k;
    return {
      variable: res.variable,
      datasets: res.datasets_requested.map((k) => ({
        key: k,
        name: name(k),
        outcome: res.results[k]?.outcome ?? "provider_error",
        message: res.results[k]?.message ?? "",
        version: res.results[k]?.entry.version ?? "",
        citation: res.results[k]?.entry.citation ?? null,
      })),
      agreementLevel: res.comparison?.agreement.level ?? null,
      agreementLabel: res.comparison ? agreementLabel(res.comparison.agreement) : null,
      directionEvidence: res.comparison?.agreement.direction_evidence ?? null,
      directionCoverage: res.comparison?.agreement.direction_coverage ?? null,
      pairsTotal: res.comparison?.agreement.pairs_total ?? null,
      pairsWithDirection: res.comparison?.agreement.pairs_with_direction ?? null,
      independenceNote: res.comparison?.agreement.independence_note
        ?? ((res.comparison?.pairs ?? []).some((p) => p.lineage !== "independent")
          ? "Some datasets share inputs or lineage (not independent), so their agreement is not an independent confirmation."
          : null),
      comparabilityNote: res.comparison?.agreement.comparability_note ?? null,
      explanation: res.comparison?.agreement.explanation ?? null,
      caution: res.comparison?.agreement.caution ?? null,
      unavailableReason: res.comparison ? null : res.comparison_unavailable_reason ?? "No comparison was produced.",
      pairs: (res.comparison?.pairs ?? []).map((p) => ({
        names: [name(p.datasets[0]), name(p.datasets[1])],
        lineage: p.lineage,
        lineageNote: p.lineage_note,
        numericallyComparable: p.numerically_comparable,
        notComparableReason: p.not_comparable_reason ?? null,
        direction: pairDirection(p),
        spearmanRho: finiteOrNull(p.spearman_rho),
        commonYears: p.common_eligible_years.length,
        unavailableReasons: p.unavailable_reasons,
      })),
      caveats: res.caveats ?? [],
    };
  }
  return null;
}

export function relationshipsFromCache(entries: [readonly unknown[], unknown][], inv: Investigation): RelationshipEvidence[] {
  const out: RelationshipEvidence[] = [];
  for (const [key, data] of entries) {
    const req = key[1] as RelKey | null | undefined;
    const res = data as RelationshipsResponse | undefined;
    if (!req || !res || (req.a !== inv.variable && req.b !== inv.variable)) continue;
    if (!near(req.lat, inv.latitude) || !near(req.lon, inv.longitude) || req.from !== inv.startYear || req.to !== inv.endYearInclusive + 1) continue;
    if (inv.variable === "soil_moisture" && inv.dataset && req.ds !== inv.dataset) continue;
    const ownSupport = res.results?.[inv.variable]?.spatial_support;
    if (ownSupport ? !spatialMatches(ownSupport, inv) : inv.mode !== "point") continue;
    out.push({
      other: req.a === inv.variable ? req.b : req.a,
      rhoAnnual: finiteOrNull(res.spearman_rho_annual),
      rhoFirstDifferences: finiteOrNull(res.spearman_rho_first_differences),
      commonYears: res.common_eligible_years,
      interpretation: res.interpretation,
      unavailableReasons: res.unavailable_reasons,
      spatialSupportsDiffer: res.alignment.spatial_supports_differ,
    });
  }
  return out;
}
