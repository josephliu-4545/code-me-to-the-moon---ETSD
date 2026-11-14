import type { Analysis, Trend } from "../api/types";

export function fmt(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs !== 0 && (abs < 0.001 || abs >= 1e6)) return value.toExponential(2);
  return value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}

export function signed(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${fmt(Math.abs(value), digits)}`;
}

export function fmtCoord(lat: number, lon: number): string {
  return `${Math.abs(lat).toFixed(4)}° ${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(4)}° ${lon >= 0 ? "E" : "W"}`;
}

const REASONS: Record<string, string> = {
  partial_calendar_year: "Partial calendar year",
  no_valid_observations: "No valid observations",
  insufficient_represented_months: "Too few months with valid data",
  insufficient_valid_slot_coverage: "Too little valid temporal coverage",
  missing_calendar_quarter: "A calendar quarter has no data",
  low_spatial_coverage_observations_excluded: "Low spatial coverage observations excluded",
  missing_catalog_month: "A monthly product is missing from the catalog",
  missing_monthly_value: "A monthly value is missing",
  insufficient_valid_months: "Fewer than 12 valid months",
  mixed_or_nonfinal_product: "Mixed or non-final product",
  no_images: "No images",
  no_valid_values: "No valid values",
  insufficient_support: "Insufficient monthly support",
  insufficient_temporal_spread: "Valid days clustered in part of the month",
  outside_availability: "Outside dataset availability",
  provisional_recent_product: "Provisional recent product (may be revised)",
  reference_incomplete: "Reference period incomplete",
};

export function reasonLabel(code: string): string {
  return REASONS[code] ?? code.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

export function dataStatusLabel(a: Analysis): { label: string; tone: "live" | "cached" | "snapshot" } {
  if (a.data_status === "saved_snapshot") {
    return { label: `Saved snapshot of a live NASA retrieval (captured ${a.snapshot?.captured_at ?? "earlier"}) — not a fresh query`, tone: "snapshot" };
  }
  if (a.data_status === "cached_nasa_retrieval" && a.cache) {
    return { label: `Cached result of a NASA retrieval at ${new Date(a.cache.retrieved_at).toLocaleString()}`, tone: "cached" };
  }
  return { label: "Live NASA data retrieval", tone: "live" };
}

export function levelTone(trend: Trend | null): "inference" | "descriptive" | "none" {
  if (!trend || trend.result_level === "annual_summaries_only") return "none";
  return trend.result_level === "statistical_inference" ? "inference" : "descriptive";
}

export function perDecade(slope: number | null): number | null {
  return slope === null ? null : slope * 10;
}

export function decadeUnits(slopeUnits: string | null): string {
  if (!slopeUnits) return "";
  if (slopeUnits.endsWith("/year²")) return slopeUnits.replace("/year²", "/year per decade");
  return slopeUnits.replace(/\/year$/, "/decade");
}

/** "p = 0.031" or "p < 0.0001", so a tiny p-value never reads as exactly zero. */
export function pText(p: number): string {
  return p < 1e-4 ? "p < 0.0001" : `p = ${fmt(p, 3)}`;
}
