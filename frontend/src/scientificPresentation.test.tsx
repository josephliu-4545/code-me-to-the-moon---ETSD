/**
 * Phase 2 scientific presentation corrections.
 * A. NDVI: the seasonal Sen slope comes from qualifying monthly values, so it is never drawn as a
 *    line through annual means (a different aggregation), and no "fitted annual" values are shown.
 * B. Dataset agreement: the headline and pair directions rest on common-period (matched) slopes and
 *    are worded as descriptive unless both datasets' own tests apply to exactly those years.
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { CompareResponse, PairComparison } from "./api/compareTypes";
import type { Analysis } from "./api/types";
import { AgreementBanner, PairTable } from "./components/compare/ComparisonPanels";
import EvidenceJourney from "./components/expedition/EvidenceJourney";
import EvidencePlot from "./components/expedition/EvidencePlot";
import TrendChart, { buildRows } from "./components/TrendChart";
import { answerQuestion } from "./detective/answers";
import { buildEvidence, toInvestigation } from "./detective/evidence";
import { classify } from "./detective/intents";
import { comparisonFromCache } from "./detective/related";
import { fittedChange } from "./lib/verdict";

const SNAPSHOTS = import.meta.glob("../public/snapshots/*.json", { eager: true, import: "default" }) as Record<string, unknown>;
const snap = (name: string) => structuredClone(SNAPSHOTS[`../public/snapshots/${name}.json`]) as Analysis;

/** Yangon temperature: an ordinary annual Theil–Sen result. */
const temperature = (): Analysis => ({ ...snap("yangon-2015-2024-temperature"), data_status: "live_nasa_retrieval" });

/** Yangon NDVI with the live seasonal result (2015–2024: Jan and Dec, 16 monthly values); every annual mean is ineligible. */
function seasonalNdvi(): Analysis {
  const a = snap("yangon-2015-2024-ndvi");
  a.data_status = "live_nasa_retrieval";
  a.trend = {
    ...a.trend!,
    method: "seasonal_kendall",
    months_used: [1, 12],
    sample_count: 16,
    result_level: "statistical_inference",
    result_level_label: "Slope with significance test (indicative; see caveat)",
    eligible_years: [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024],
    slope: 0.001471659030787593,
    intercept: -2.4071,
    slope_units: "NDVI units/year",
    confidence_interval: [-0.006507587728551334, 0.013189374877778492],
    confidence_interval_unavailable_reason: null,
    mann_kendall: { s: 2, tau: 0.0357, p_value: 0.9302885701156911, alpha: 0.05, is_statistically_significant: false, direction: "no_detected_trend" },
    slope_unavailable_reason: null,
    significance_unavailable_reason: null,
  };
  return a;
}

describe("A · NDVI annual chart", () => {
  it("draws no seasonal fitted line through annual means", () => {
    expect(buildRows(seasonalNdvi()).every((r) => r.trend === null)).toBe(true);
  });

  it("keeps the Theil–Sen line for ordinary annual trends", () => {
    const a = temperature();
    const rows = buildRows(a).filter((r) => r.trend !== null);
    expect(rows.length).toBe(10);
    expect(rows[0]!.trend).toBeCloseTo(a.trend!.intercept! + a.trend!.slope! * rows[0]!.year, 10);
  });

  it("titles, legends, captions and tables describe only what is drawn", () => {
    const { container } = render(<TrendChart analysis={seasonalNdvi()} />);
    expect(screen.getByRole("heading", { name: "Annual values" })).toBeInTheDocument();
    const legend = screen.getByRole("list", { name: "Legend" });
    expect(within(legend).queryByText(/trend/i)).toBeNull();
    const caption = container.querySelector("figcaption")!.textContent!;
    expect(caption).toMatch(/qualifying monthly values/);
    expect(caption).toMatch(/not drawn on this chart/);
    expect(caption).toMatch(/Seasonal Sen slope/);
    expect(screen.queryByRole("columnheader", { name: /Fitted trend/ })).toBeNull();
  });

  it("still labels the Theil–Sen line and its table column for annual trends", () => {
    render(<TrendChart analysis={temperature()} />);
    expect(screen.getByRole("heading", { name: "Annual values and fitted trend" })).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Legend" })).getByText(/Theil–Sen trend/)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /Fitted trend/ })).toBeInTheDocument();
  });

  it("reports no 'along the fitted line' change for the seasonal method", () => {
    expect(fittedChange(seasonalNdvi())).toBeNull();
    expect(fittedChange(temperature())).not.toBeNull();
  });

  it("the evidence plot draws no seasonal line and does not say dots shaped a line", () => {
    const { container: seasonal } = render(<EvidencePlot analysis={seasonalNdvi()} focusYear={null} />);
    expect(seasonal.querySelector(".ep-trend")).toBeNull();
    const { container: annual } = render(<EvidencePlot analysis={temperature()} focusYear={null} />);
    expect(annual.querySelector(".ep-trend")).not.toBeNull();
    render(<EvidenceJourney analysis={seasonalNdvi()} stage="trend" onStage={() => {}} focusYear={null} onFocusYear={() => {}} onOpenLab={() => {}} />);
    expect(screen.queryByText(/shaped the line/)).toBeNull();
    expect(screen.getByText(/qualifying monthly values/)).toBeInTheDocument();
  });
});

// ---------------- B · dataset agreement ----------------

function pair(over: Partial<PairComparison> = {}): PairComparison {
  return {
    datasets: ["a", "b"], lineage: "partially_related", lineage_note: "Reanalyses share assimilated observations.",
    numerically_comparable: true, common_eligible_years: [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024],
    full_period_slopes: { a: 0.02, b: 0.03 }, common_period_slopes: { a: 0.02, b: -0.01 },
    common_period_slope_sign_agreement: false, slope_sign_agreement: true, confidence_intervals_overlap: null,
    annual_differences: null, mean_difference: 0.4, mean_absolute_difference: 0.4, spearman_rho: 0.6, pearson_r: 0.6,
    spearman_rho_year_to_year: 0.5, unavailable_reasons: [], direction_evidence: "descriptive_opposite_direction", ...over,
  } as PairComparison;
}

function response(level: string, extra: Record<string, unknown> = {}, p: PairComparison = pair()): CompareResponse {
  return {
    variable: "temperature", location: { latitude: 16.8661, longitude: 96.1951, mode: "point" },
    period: { start: "2015-01-01", end_exclusive: "2025-01-01" }, datasets_requested: ["a", "b"], datasets_are_merged: false,
    results: {
      a: { entry: { name: "Dataset A", version: "1", citation: null }, outcome: "inference", message: "", analysis: null },
      b: { entry: { name: "Dataset B", version: "2", citation: null }, outcome: "inference", message: "", analysis: null },
    },
    succeeded: ["a", "b"],
    comparison: {
      pairs: [p], all_numerically_comparable: true, common_eligible_years_all: p.common_eligible_years,
      agreement: { level, slope_sign_agreement_all: false, min_spearman_rho: 0.6, explanation: "Backend explanation.", caution: "Agreement between datasets does not prove accuracy.", ...extra },
      method: {},
    },
    comparison_unavailable_reason: null, caveats: [],
  } as unknown as CompareResponse;
}

describe("B · dataset agreement presentation", () => {
  it("never labels opposite descriptive slopes as a conflict", () => {
    render(<AgreementBanner data={response("conflicting_trend_direction")} />);
    const banner = screen.getByRole("status");
    expect(banner).not.toHaveTextContent(/Conflicting/i);
    expect(banner).toHaveTextContent(/Opposite descriptive slope directions/);
    expect(banner).toHaveTextContent(/common eligible years/);
  });

  it("uses the backend's cautious label when provided", () => {
    render(<AgreementBanner data={response("consistent", { label: "Same descriptive direction, strong co-variation", direction_evidence: "descriptive" })} />);
    expect(screen.getByRole("status")).toHaveTextContent("Same descriptive direction, strong co-variation");
    expect(screen.getByRole("status")).toHaveTextContent(/descriptive/i);
  });

  it("pair table shows the common-period direction, not the full-request sign", () => {
    render(<PairTable data={response("conflicting_trend_direction")} />);
    expect(screen.getByRole("columnheader", { name: /Direction over common years/ })).toBeInTheDocument();
    const row = screen.getAllByRole("row")[1]!;
    expect(row).toHaveTextContent(/Opposite \(descriptive\)/);
    expect(row).not.toHaveTextContent(/\byes\b/);
  });

  it("marks direction unavailable below three common years", () => {
    const short = pair({ common_eligible_years: [2017, 2018], common_period_slopes: null, common_period_slope_sign_agreement: null, direction_evidence: "unavailable" });
    render(<PairTable data={response("not_assessable", {}, short)} />);
    expect(screen.getAllByRole("row")[1]).toHaveTextContent(/Not assessable/);
  });

  it("the Detective reports common-period, descriptive directions and shared inputs", () => {
    const inv = toInvestigation({ variable: "temperature", latitude: 16.8661, longitude: 96.1951, startYear: 2015, endYear: 2025, mode: "point" }, "Air temperature (2 m)", "Yangon");
    const key = ["compare", { variable: "temperature", datasets: ["a", "b"], latitude: 16.8661, longitude: 96.1951, startYear: 2015, endYear: 2025 }] as const;
    const c = comparisonFromCache([[key, response("conflicting_trend_direction", { label: "Opposite descriptive slope directions", direction_evidence: "descriptive" })]], inv);
    const e = buildEvidence(temperature(), inv);
    const text = answerQuestion(classify("Why do the datasets disagree?", null), e, { comparison: c, relationships: [] }).sections.flatMap((s) => s.lines).join("\n");
    expect(text).toMatch(/opposite \(descriptive\) over common years/);
    expect(text).not.toMatch(/slope signs (agree|differ)/);
    expect(text).toMatch(/Opposite descriptive slope directions/);
    expect(text).not.toMatch(/conflicting_trend_direction|Conflicting/);
    expect(text).toMatch(/not an established (agreement|conflict)/);
    expect(text).toMatch(/shared inputs|not independent/);
  });
});

describe("B · partial pair coverage (PR #9 review)", () => {
  it("the banner says only some pairs were compared and never generalises", () => {
    render(<AgreementBanner data={response("partially_assessable", { direction_coverage: "partial", pairs_total: 3, pairs_with_direction: 1 })} />);
    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent(/Partially assessable/);
    expect(banner).toHaveTextContent(/1 of 3 dataset pairs/);
    expect(banner).toHaveTextContent(/pair table/);
    expect(banner).not.toHaveTextContent(/Opposite descriptive|Same descriptive|Mixed/);
  });

  it("the Detective keeps pairwise findings but states the headline is partial", () => {
    const inv = toInvestigation({ variable: "temperature", latitude: 16.8661, longitude: 96.1951, startYear: 2015, endYear: 2025, mode: "point" }, "Air temperature (2 m)", "Yangon");
    const key = ["compare", { variable: "temperature", datasets: ["a", "b"], latitude: 16.8661, longitude: 96.1951, startYear: 2015, endYear: 2025 }] as const;
    const resp = response("partially_assessable", { label: "Partially assessable: 1 of 3 pairs compared", direction_coverage: "partial", pairs_total: 3, pairs_with_direction: 1 });
    const c = comparisonFromCache([[key, resp]], inv);
    const e = buildEvidence(temperature(), inv);
    const text = answerQuestion(classify("Why do the datasets disagree?", null), e, { comparison: c, relationships: [] }).sections.flatMap((s) => s.lines).join("\n");
    expect(text).toMatch(/Partially assessable: 1 of 3 pairs compared/);
    expect(text).toMatch(/Only 1 of 3 dataset pairs could be compared/);
    expect(text).toMatch(/Dataset A vs Dataset B: partially related; 10 common eligible years; opposite \(descriptive\) over common years/);
  });

  it("falls back to a cautious label for partial coverage from older responses", () => {
    render(<AgreementBanner data={response("partially_assessable")} />);
    expect(screen.getByRole("status")).toHaveTextContent(/Partially assessable/);
  });
});
