/**
 * Layer 3 support — related evidence the user has ALREADY produced elsewhere in the app.
 *
 * Compare Datasets and Earth System Relationships results are read from the TanStack Query
 * cache only when they match the active investigation's location and period. Nothing here
 * starts a retrieval: if the evidence is not in the cache, the assistant says which analysis to run.
 */
import type { CompareRequest } from "../api/compareClient";
import type { CompareResponse } from "../api/compareTypes";
import type { RelationshipsResponse } from "../api/types";
import { finiteOrNull, type Investigation } from "./evidence";

export interface ComparisonEvidence {
  variable: string;
  datasets: { key: string; name: string; outcome: string; message: string; version: string; citation: string | null }[];
  agreementLevel: string | null;
  explanation: string | null;
  caution: string | null;
  unavailableReason: string | null;
  pairs: {
    names: [string, string];
    lineage: string;
    lineageNote: string;
    numericallyComparable: boolean;
    notComparableReason: string | null;
    slopeSignAgreement: boolean | null;
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

export function comparisonFromCache(entries: [readonly unknown[], unknown][], inv: Investigation): ComparisonEvidence | null {
  for (const [key, data] of entries) {
    const req = key[1] as CompareRequest | null | undefined;
    const res = data as CompareResponse | undefined;
    if (!req || !res || req.variable !== inv.variable) continue;
    if (!near(req.latitude, inv.latitude) || !near(req.longitude, inv.longitude)) continue;
    if (req.startYear !== inv.startYear || req.endYear !== inv.endYearInclusive + 1) continue;
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
      explanation: res.comparison?.agreement.explanation ?? null,
      caution: res.comparison?.agreement.caution ?? null,
      unavailableReason: res.comparison ? null : res.comparison_unavailable_reason ?? "No comparison was produced.",
      pairs: (res.comparison?.pairs ?? []).map((p) => ({
        names: [name(p.datasets[0]), name(p.datasets[1])],
        lineage: p.lineage,
        lineageNote: p.lineage_note,
        numericallyComparable: p.numerically_comparable,
        notComparableReason: p.not_comparable_reason ?? null,
        slopeSignAgreement: p.slope_sign_agreement,
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
