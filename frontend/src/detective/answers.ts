/**
 * Layers 3 and 4 — evidence selection and answer construction.
 *
 * Deterministic templates fill in values copied from the evidence object. Every answer separates
 * observed facts, statistical interpretation, uncertainty, general background and hypotheses,
 * and lists the evidence it used. When the evidence cannot answer, the answer says so and names
 * the analysis that would be needed. No numbers are invented and no citations are constructed.
 */
import type { DirectionEvidence } from "../api/compareTypes";
import { ESTIMATOR_READING } from "../components/methodslab/MethodsLab";
import { directionLabel } from "../lib/agreement";
import { pText, reasonLabel } from "../lib/format";
import type { Evidence } from "./evidence";
import { INTENT_LABELS, type Classification, type Intent } from "./intents";
import type { RelatedEvidence } from "./related";
import { redactSecrets } from "./safety";

export type AnswerStatus = "supported" | "descriptive" | "indicative" | "needs_analysis" | "not_answerable" | "guidance";

export const STATUS_LABELS: Record<AnswerStatus, string> = {
  supported: "Supported by current analysis",
  descriptive: "Descriptive evidence only",
  indicative: "Indicative statistical evidence",
  needs_analysis: "Additional analysis required",
  not_answerable: "Not answerable with current evidence",
  guidance: "How-to guidance",
};

export type SectionKind = "finding" | "statistics" | "uncertainty" | "background" | "hypothesis" | "limitations" | "next_steps" | "notice";

export const SECTION_TITLES: Record<SectionKind, string> = {
  finding: "Finding",
  statistics: "Statistical evidence",
  uncertainty: "Uncertainty",
  background: "Background scientific context (not a finding of this analysis)",
  hypothesis: "Possible explanations — unverified hypotheses",
  limitations: "Limitations",
  next_steps: "What you can do next",
  notice: "Notice",
};

export interface Section {
  kind: SectionKind;
  lines: string[];
}

export interface Source {
  label: string;
  detail: string;
  href?: string;
}

export interface Answer {
  intent: Intent | null;
  topic: string;
  status: AnswerStatus;
  sections: Section[];
  sources: Source[];
  suggestions: string[];
}

// ---------- number formatting (display only; never alters the stored value) ----------

/** Three significant figures, true minus sign; null stays "unavailable", never 0. */
export function num(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "unavailable";
  if (v === 0) return "0";
  const abs = Math.abs(v);
  const s = abs >= 1000 ? Math.round(abs).toLocaleString("en-US") : String(Number(abs.toPrecision(3)));
  return `${v < 0 ? "−" : ""}${s}`;
}
const signedNum = (v: number | null) => (v !== null && v > 0 ? `+${num(v)}` : num(v));
const years = (ys: number[]) => (ys.length ? ys.join(", ") : "none");
const span = (ys: number[]) => (ys.length ? `${Math.min(...ys)}–${Math.max(...ys)}` : "no eligible years");

// ---------- shared pieces ----------

function lower(name: string): string {
  return /^[A-Z][a-z]/.test(name) ? name[0]!.toLowerCase() + name.slice(1) : name;
}

function datasetSource(e: Evidence): Source {
  const d = e.dataset;
  const detail = [`Version: ${d.version}`, `Type: ${d.provenance}`, d.citation ? `Citation: ${d.citation}` : null, d.doi ? `DOI: ${d.doi}` : "No DOI is listed in the application's dataset catalog."]
    .filter(Boolean)
    .join(" · ");
  return { label: `${d.source} — ${d.title ?? d.id}`, detail, href: d.doi ? `https://doi.org/${d.doi}` : undefined };
}

function analysisSource(e: Evidence): Source {
  return { label: "Trend analysis in this application", detail: `${e.trend.estimator} and ${e.trend.test}; result level: ${e.trend.resultLevelLabel ?? "not reported"}`, href: "#evaluation" };
}

const methodsSource: Source = { label: "Statistical Methods Lab", detail: "Method definitions and the OLS versus Theil–Sen comparison on the same eligible years", href: "#evaluation" };
const guideSource: Source = { label: "Scientific Information", detail: "The application's field guide to datasets, methods and caveats", href: "#science" };

function eligibleYears(e: Evidence): number[] {
  return e.observations.eligible.map((o) => o.year);
}

function scopeLine(e: Evidence): string {
  return `This describes ${e.dataset.source} (${e.dataset.id}) for ${lower(e.footprint.description)} at ${e.footprint.resolution} resolution, over the requested period ${e.periodLabel}. It is not a measurement at an exact address.`;
}

const NOT_CAUSE = "A trend analysis describes change in this dataset; it does not, by itself, identify what caused the change.";

function snapshotNotice(e: Evidence): Section[] {
  if (e.dataStatus.kind !== "saved_snapshot") return [];
  return [{ kind: "notice", lines: [`These results come from a saved snapshot of an earlier live NASA retrieval (captured ${e.dataStatus.snapshotCapturedAt ?? "earlier"}). They are not a fresh query, and evidence added to the application after that date (such as the Statistical Methods Lab) may be missing.`] }];
}

function slopeSentence(e: Evidence): string {
  const ys = eligibleYears(e);
  const basis = e.seasonal ? `using ${e.seasonal.sampleCount ?? "the"} monthly values from ${e.seasonal.months.join(", ") || "no months"}` : `on ${ys.length} eligible years (${span(ys)})`;
  return `According to the selected ${e.dataset.source} analysis, the estimated ${lower(e.variableName)} trend (${e.trend.estimator}) is ${signedNum(e.trend.slope)} ${e.units.slope ?? ""}, ${basis}.`;
}

/** Region investigations cannot borrow point-based comparison or relationship results. */
function regionNote(e: Evidence): string {
  return e.investigation.mode === "region"
    ? "This is a region investigation. Cached Compare Datasets or Earth System Relationships results for a single point are not used as evidence for this region; an analysis of the same region would be needed."
    : "";
}

/** Coverage in the terms of the method actually used (annual years, or months for the seasonal method). */
function coverageSentence(e: Evidence): string {
  if (e.seasonal) {
    return `The seasonal trend uses monthly values from ${e.seasonal.months.join(", ") || "no months"} in ${e.seasonal.yearsContributing.length} contributing years (${span(e.seasonal.yearsContributing)}); annual-value exclusions do not remove years from it.`;
  }
  return `${eligibleYears(e).length} of ${e.observations.yearsRequested} requested years passed the eligibility rules; ${e.observations.excluded.length} were excluded.`;
}

function statusForTrend(e: Evidence): AnswerStatus {
  switch (e.trend.verdict) {
    case "increasing":
    case "decreasing":
      return "indicative";
    case "not_detected":
      return "supported";
    case "descriptive":
      return "descriptive";
    default:
      return "not_answerable";
  }
}

function significanceLines(e: Evidence): string[] {
  const s = e.trend.significance;
  if (!s) {
    return [`No significance test is reported for this result.${e.trend.significanceUnavailableReason ? ` Reason given by the analysis: ${e.trend.significanceUnavailableReason}.` : ""} Any direction is therefore descriptive only.`];
  }
  const out = s.significant
    ? `The ${e.trend.test} test gives ${pText(s.pValue)}, below the α = ${s.alpha} threshold, so it rejects “no monotonic trend”. This is indicative evidence, not proof.`
    : `The ${e.trend.test} test gives ${pText(s.pValue)}, which is not below α = ${s.alpha}, so no monotonic trend was detected. That is consistent with no trend, but it is not proof that nothing changed.`;
  return [out, e.trend.verdictNote];
}

function intervalLines(e: Evidence): string[] {
  const ci = e.trend.confidenceInterval;
  if (!ci) {
    return [`No confidence interval is reported for this slope${e.trend.confidenceIntervalUnavailableReason ? `: ${e.trend.confidenceIntervalUnavailableReason}` : ""}. None has been estimated in its place.`];
  }
  const zero = ci[0] <= 0 && ci[1] >= 0
    ? "The interval includes zero, so the data are also consistent with no change over this period."
    : `The interval excludes zero; within it the slope is consistently ${ci[0] > 0 ? "positive" : "negative"}, subject to the caveats of the method.`;
  return [`The 95% interval for the ${e.trend.estimator} is ${num(ci[0])} to ${num(ci[1])} ${e.units.slope ?? ""}.`, zero];
}

function unavailableTrend(e: Evidence): Answer {
  return answer("direction", "not_answerable", [
    { kind: "finding", lines: [`A trend cannot be stated for this investigation. ${e.trend.slopeUnavailableReason ?? e.trend.verdictNote}`] },
    { kind: "limitations", lines: [`Eligible years: ${eligibleYears(e).length} of ${e.observations.yearsRequested} requested. Unavailable values are left out; they are never replaced by zero or estimates.`] },
    { kind: "next_steps", lines: ["Try a longer period or another location, or see which years were excluded and why."] },
  ], [analysisSource(e), datasetSource(e)], e);
}

function answer(intent: Intent | null, status: AnswerStatus, sections: Section[], sources: Source[], e: Evidence | null, extra: string[] = []): Answer {
  const clean = sections.map((s) => ({ ...s, lines: s.lines.filter(Boolean).map(redactSecrets) }));
  const notice = e ? snapshotNotice(e) : [];
  return {
    intent,
    topic: intent ? INTENT_LABELS[intent] : "Clarification",
    status,
    sections: [...notice, ...clean],
    sources,
    suggestions: extra.length ? extra : e ? suggestedQuestions(e, null).slice(0, 3) : [],
  };
}

/** Pair direction over common eligible years, in words. */
function pairDirectionText(d: DirectionEvidence): string {
  if (d === "unavailable") return "direction not assessable (fewer than 3 common eligible years)";
  if (d === "descriptive_no_direction") return "no direction (a slope over common years is exactly zero)";
  return `${directionLabel({ direction_evidence: d, common_period_slope_sign_agreement: null }).toLowerCase()} over common years`;
}

// ---------- general background (labelled; mechanisms are possibilities, never findings) ----------

const MECHANISMS: Record<string, string[]> = {
  temperature: [
    "Large-scale climate forcing, including rising greenhouse-gas concentrations.",
    "Natural year-to-year and decade-to-decade variability, for example from modes such as the El Niño–Southern Oscillation.",
    "Local land-surface change, such as urban expansion or changes in vegetation and surface moisture.",
  ],
  extreme_heat: [
    "A shift in average temperature changes how often a fixed heat threshold is exceeded.",
    "Natural variability between years and decades.",
    "Local land-surface change, such as urban expansion.",
  ],
  relative_humidity: [
    "Temperature changes: warmer air can hold more water vapour, so relative humidity can fall even when moisture is unchanged.",
    "Variability in monsoon and large-scale circulation.",
    "Changes in surface moisture, vegetation or irrigation.",
  ],
  precipitation: [
    "Variability in monsoon and large-scale circulation between years and decades.",
    "Precipitation varies strongly from year to year, so short records can show slopes that do not persist.",
    "Changes in the satellite inputs or retrieval methods behind the product.",
  ],
  ndvi: [
    "Land-cover or land-use change, such as urban expansion, agriculture or forest change.",
    "Year-to-year rainfall and temperature conditions that affect plant growth.",
    "Cloud contamination and sensor processing, which affect what the satellite can observe.",
  ],
  soil_moisture: [
    "The balance between precipitation and evaporation.",
    "Irrigation or land-use change.",
    "Model inputs (for GLDAS) or retrieval algorithms (for SMAP), which shape what each product represents.",
  ],
};

const ATTRIBUTION_EVIDENCE = [
  "A longer record: climate is usually described over multiple decades (often 30 years), and short records are strongly affected by natural variability.",
  "Agreement between independent datasets for the same place and period (see Compare Datasets).",
  "Accounting for natural variability (for example, known modes of year-to-year variability) before interpreting a trend.",
  "Comparisons with nearby reference areas and land-use or land-cover records, to separate local from regional change.",
  "Physically consistent changes in related variables (see Earth System Relationships), which still indicate association, not cause.",
  "Formal detection-and-attribution studies using climate models — these are outside the scope of this application.",
];

// ---------- suggested questions ----------

export function suggestedQuestions(e: Evidence | null, related: RelatedEvidence | null): string[] {
  if (!e) return ["How do I start an Earth investigation?", "What can I ask you?"];
  const out: string[] = [];
  const name = lower(e.variableName.replace(/\s*\([^)]*\)/g, "")); // "Air temperature (2 m)" → "air temperature"
  if (e.trend.slope !== null) out.push(`Is ${name} increasing?`, "How much has it changed?", "What are its limitations?");
  else out.push("Why couldn't a trend be calculated?");
  if (e.trend.significance) out.push("Is this trend statistically significant?");
  else if (e.trend.slope !== null) out.push("Why couldn't significance be calculated?");
  if (e.trend.confidenceInterval) out.push("What does the confidence interval mean?");
  if (e.seasonal) out.push("Why does this analysis use Seasonal Kendall?", "Which months contributed to the trend?");
  if (e.observations.excluded.length) out.push("Which years were excluded?");
  if (e.variableId === "soil_moisture") out.push("Which observations passed quality control?", "How do GLDAS and SMAP differ?");
  if (e.methodsLab && e.methodsLab.olsSlope !== null) out.push("What is the difference between OLS and Theil–Sen?");
  if (related?.comparison) out.push("Why do the datasets disagree?");
  out.push("Why is this happening?", "Can I trust these results?");
  return [...new Set(out)];
}

// ---------- main entry ----------

export function answerQuestion(c: Classification, e: Evidence | null, related: RelatedEvidence | null): Answer {
  if (c.intent === "injection") {
    return answer("injection", "guidance", [
      { kind: "notice", lines: ["Your question contained instructions about how to answer. Instructions inside questions are not followed: answers come only from the analysis evidence, under fixed rules that cannot be changed from the chat."] },
    ], [], e);
  }
  if (c.intent === "secrets") {
    return answer("secrets", "not_answerable", [
      { kind: "notice", lines: ["The assistant has no access to credentials, API keys, environment files or server configuration, and cannot reveal them. It only sees the scientific results already shown in the application."] },
    ], [], e);
  }
  if (c.status === "ambiguous") {
    return answer(null, "guidance", [
      { kind: "notice", lines: [c.candidates.length ? `Your question could mean more than one thing: ${c.candidates.map((i) => INTENT_LABELS[i].toLowerCase()).join(" or ")}. Which did you mean?` : "Could you say a little more about what you would like to know?"] },
    ], [], e, c.candidates.map(exampleFor));
  }
  if (c.status === "unsupported" || !c.intent) {
    return answer(null, "not_answerable", [
      { kind: "notice", lines: ["I couldn't match that question to something the available evidence can answer. I answer questions about the current investigation's trend, significance, uncertainty, data coverage, datasets and methods. Try one of the suggestions below."] },
    ], [], e);
  }
  if (c.intent === "getting_started") return gettingStarted(e);
  if (c.intent === "prediction") {
    return answer("prediction", "not_answerable", [
      { kind: "notice", lines: ["Forecasting is not part of this application. Trend slopes describe the analysed period only and must not be extended into the future."] },
    ], e ? [analysisSource(e)] : [], e);
  }
  if (!e) {
    return answer(c.intent, "needs_analysis", [
      { kind: "notice", lines: ["There is no completed investigation to use as evidence yet. Choose a place, variable and period in Explore Earth and launch an investigation, then come back to ask about it."] },
    ], [], null, ["How do I start an Earth investigation?"]);
  }
  return BUILDERS[c.intent](e, related);
}

function exampleFor(i: Intent): string {
  const examples: Partial<Record<Intent, string>> = {
    causality_why: "What could be causing this trend?",
    why_no_significance: "Why couldn't significance be calculated?",
    direction: "Is it increasing?",
    magnitude: "How much has it changed?",
    significance: "Is this trend statistically significant?",
    methodology: "How was the trend calculated?",
    reliability: "Can I trust these results?",
    excluded: "Which years were excluded?",
    missing: "What does the missing data mean?",
    provenance: "Which dataset was used?",
    dataset_disagreement: "Why do the datasets disagree?",
    confidence_interval: "What does the confidence interval mean?",
  };
  return examples[i] ?? INTENT_LABELS[i];
}

function gettingStarted(e: Evidence | null): Answer {
  return answer("getting_started", "guidance", [
    { kind: "next_steps", lines: [
      "1. Open Explore Earth, pick a place on the map or search for one.",
      "2. Choose a variable (for example air temperature or vegetation greenness) and a period.",
      "3. Launch the investigation and wait for the NASA data to be retrieved and analysed.",
      "4. Return here and ask about the result — or pick a suggested question.",
      e ? `An investigation is already active: ${e.variableName}, ${e.investigation.place}, ${e.periodLabel}.` : "",
      "This assistant is rule-based: it matches your question to supported topics and answers from the analysis results. It does not use a generative language model.",
    ] },
  ], [], e, e ? suggestedQuestions(e, null).slice(0, 3) : ["How do I start an Earth investigation?"]);
}

type Builder = (e: Evidence, r: RelatedEvidence | null) => Answer;

const BUILDERS: Record<Exclude<Intent, "injection" | "secrets" | "getting_started" | "prediction">, Builder> = {
  overview(e) {
    if (e.trend.verdict === "unavailable") return { ...unavailableTrend(e), intent: "overview", topic: INTENT_LABELS.overview };
    return answer("overview", statusForTrend(e), [
      { kind: "finding", lines: [`${e.trend.verdictLabel}. ${slopeSentence(e)}`, coverageSentence(e)] },
      { kind: "statistics", lines: significanceLines(e) },
      { kind: "uncertainty", lines: intervalLines(e) },
      { kind: "limitations", lines: [scopeLine(e), NOT_CAUSE] },
    ], [datasetSource(e), analysisSource(e)], e);
  },

  direction(e) {
    if (e.trend.verdict === "unavailable") return unavailableTrend(e);
    return answer("direction", statusForTrend(e), [
      { kind: "finding", lines: [slopeSentence(e)] },
      { kind: "statistics", lines: significanceLines(e) },
      { kind: "limitations", lines: [scopeLine(e), NOT_CAUSE] },
    ], [datasetSource(e), analysisSource(e)], e);
  },

  magnitude(e) {
    if (e.trend.verdict === "unavailable") return { ...unavailableTrend(e), intent: "magnitude", topic: INTENT_LABELS.magnitude };
    const fc = e.trend.fittedChange;
    return answer("magnitude", statusForTrend(e), [
      { kind: "finding", lines: [
        slopeSentence(e),
        fc && !e.seasonal ? `Along the fitted line this amounts to ${signedNum(fc.value)} ${e.units.annual} between ${fc.from} and ${fc.to}. That is a property of the fitted line, not the observed difference between those two years.` : "",
      ] },
      { kind: "uncertainty", lines: intervalLines(e) },
      { kind: "statistics", lines: significanceLines(e) },
      { kind: "limitations", lines: [scopeLine(e)] },
    ], [analysisSource(e), datasetSource(e)], e);
  },

  significance(e) {
    if (!e.trend.significance) return BUILDERS.why_no_significance(e, null);
    const s = e.trend.significance;
    return answer("significance", s.significant ? "indicative" : "supported", [
      { kind: "statistics", lines: [...significanceLines(e), `Kendall τ = ${num(s.tau)}.`] },
      { kind: "background", lines: ["A p-value is the probability of a result at least this extreme if there were no monotonic trend. It is not the probability that there is no trend, and it says nothing about cause."] },
      { kind: "limitations", lines: [e.trend.dependence ? `Serial-dependence screen: ${e.trend.dependence.caveat}` : "", scopeLine(e)] },
    ], [analysisSource(e), methodsSource], e);
  },

  why_no_significance(e) {
    const s = e.trend.significance;
    if (s) {
      return answer("why_no_significance", s.significant ? "indicative" : "supported", [
        { kind: "statistics", lines: [`A significance test was run for this investigation. ${significanceLines(e)[0]}`] },
        { kind: "limitations", lines: [e.trend.dependence?.caveat ?? ""] },
      ], [analysisSource(e), methodsSource], e);
    }
    const dep = e.trend.dependence;
    const lines = [
      e.trend.significanceUnavailableReason ? `The analysis withheld the significance test. Reason given: ${e.trend.significanceUnavailableReason}.` : `No significance test is reported (result level: ${e.trend.resultLevelLabel ?? "not reported"}).`,
      dep && !dep.supportsInference ? `The lag-1 serial-dependence screen reported “${dep.status.replace(/_/g, " ")}”${dep.rho !== null ? ` (lag-1 Spearman ρ = ${num(dep.rho)})` : ""}. Correlated neighbouring years make standard p-values too optimistic, so the test is withheld rather than reported misleadingly.` : "",
      `Eligible years available: ${eligibleYears(e).length}.`,
    ];
    return answer("why_no_significance", e.trend.slope !== null ? "descriptive" : "not_answerable", [
      { kind: "statistics", lines },
      { kind: "limitations", lines: [e.trend.slope !== null ? "The slope is still reported, but only as a description." : "No slope could be estimated either.", "Unavailable results are never shown as zero or as “no trend”."] },
    ], [analysisSource(e), methodsSource], e);
  },

  confidence_interval(e) {
    return answer("confidence_interval", e.trend.confidenceInterval ? "supported" : "not_answerable", [
      { kind: "uncertainty", lines: intervalLines(e) },
      { kind: "background", lines: [`The interval describes uncertainty in the ${e.trend.estimator} only. It is not an interval for an OLS slope, for the difference between estimators, or for individual years.`] },
    ], [analysisSource(e), methodsSource], e);
  },

  causality_why(e) {
    const observed = e.trend.verdict === "unavailable"
      ? "No trend could be established for this investigation, so there is no detected change to explain."
      : e.trend.verdict === "not_detected"
        ? `${slopeSentence(e)} However, no monotonic trend was detected, so there may be no real change to explain.`
        : e.trend.verdict === "descriptive"
          ? `${slopeSentence(e)} No significance test is reported, so even the direction is descriptive only.`
          : slopeSentence(e);
    return answer("causality_why", "not_answerable", [
      { kind: "finding", lines: [observed] },
      { kind: "hypothesis", lines: [`In general, ${lower(e.variableName)} at a location can change because of several mechanisms. None of these is identified by this analysis:`, ...(MECHANISMS[e.variableId] ?? ["Several physical and data-related mechanisms are possible."]).map((m) => `• ${m}`)] },
      { kind: "limitations", lines: [NOT_CAUSE, "Establishing a cause needs additional evidence; ask “What evidence would be needed to investigate the cause?”"] },
    ], [analysisSource(e), guideSource], e, ["What evidence would be needed to investigate the cause?", "Does this prove climate change caused the result?", "Can I trust these results?"]);
  },

  causality_proof(e) {
    const ys = eligibleYears(e);
    return answer("causality_proof", "not_answerable", [
      { kind: "finding", lines: ["No. This analysis cannot show that climate change — or any other factor — caused the result."] },
      { kind: "statistics", lines: [`It estimates a trend in one dataset (${e.dataset.source}) for one footprint over ${ys.length} eligible years (${span(ys)}). Even a statistically significant trend shows a consistent direction, not its cause.`] },
      { kind: "background", lines: ["Attributing a local change to climate change requires long records, independent datasets, accounting for natural variability and local factors, and formal attribution methods."] },
      { kind: "limitations", lines: [NOT_CAUSE] },
    ], [analysisSource(e), guideSource], e, ["What evidence would be needed to investigate the cause?", "Why is this happening?"]);
  },

  cause_evidence(e) {
    return answer("cause_evidence", "guidance", [
      { kind: "background", lines: ["Investigating a cause would need evidence this analysis does not provide, for example:", ...ATTRIBUTION_EVIDENCE.map((x) => `• ${x}`)] },
      { kind: "limitations", lines: [`The current investigation covers ${eligibleYears(e).length} eligible years from one dataset.`] },
    ], [guideSource, { label: "Compare Datasets", detail: "Check whether independent datasets agree", href: "#compare" }, { label: "Earth System Relationships", detail: "Check association with another variable", href: "#relationships" }], e);
  },

  reliability(e) {
    const m = e.monthly;
    const dep = e.trend.dependence;
    const cp = e.trend.changePoint;
    return answer("reliability", statusForTrend(e) === "not_answerable" ? "not_answerable" : "supported", [
      { kind: "finding", lines: [
        `Data status: ${e.dataStatus.label}.`,
        `Dataset: ${e.dataset.source} ${e.dataset.id} (${e.dataset.version}), a ${e.dataset.provenance}.`,
        `Coverage: ${coverageSentence(e)}${m ? ` ${m.valid} of ${m.expected} monthly values had valid data.` : ""}`,
        `Result level: ${e.trend.resultLevelLabel ?? "not reported"}.`,
      ] },
      { kind: "statistics", lines: [
        dep ? `Serial dependence: ${dep.caveat}` : "",
        cp?.status === "step_detected" ? `An abrupt step was detected between ${cp.last_year_before} and ${cp.first_year_after}; a single straight-line trend may misrepresent this record.` : cp?.status === "none" ? "No abrupt step was detected." : cp?.reason ? `Change-point check not run: ${cp.reason}` : "",
      ] },
      { kind: "limitations", lines: [...e.caveats.slice(0, 3), scopeLine(e)] },
    ], [datasetSource(e), analysisSource(e)], e);
  },

  excluded(e) {
    const ex = e.observations.excluded;
    if (e.seasonal) {
      return answer("excluded", "supported", [
        { kind: "finding", lines: [
          `The NDVI trend uses the Seasonal Kendall method on monthly values, not annual values. ${coverageSentence(e)}`,
          ex.length ? `Under the separate annual-value rules, ${ex.length} of ${e.observations.yearsRequested} years have no eligible annual summary:` : "No year was excluded from the annual summaries.",
          ...ex.map((x) => `• ${x.year}: ${x.reasons.length ? x.reasons.join("; ") : "no annual value"}`),
        ] },
        { kind: "limitations", lines: ["Months that do not have data in enough years are left out of the trend, not filled in."] },
      ], [analysisSource(e), datasetSource(e)], e);
    }
    return answer("excluded", "supported", [
      { kind: "finding", lines: ex.length
        ? [`${ex.length} of ${e.observations.yearsRequested} requested years were excluded from the trend:`, ...ex.map((x) => `• ${x.year}: ${x.reasons.length ? x.reasons.join("; ") : "no annual value"}`)]
        : [`None of the ${e.observations.yearsRequested} requested years were excluded; all passed the eligibility and quality-control rules.`] },
      { kind: "limitations", lines: ["Excluded years are left out of the trend. Their values are never replaced by zeros or estimates.", e.seasonal ? "This NDVI analysis uses monthly values; ask which months contributed." : ""] },
    ], [analysisSource(e), datasetSource(e)], e);
  },

  missing(e) {
    const m = e.monthly;
    const miss = e.observations.missingYears;
    return answer("missing", "supported", [
      { kind: "finding", lines: [
        m ? `${m.valid} of ${m.expected} monthly values had valid data across the years that report monthly coverage.` : "This dataset does not report month-by-month coverage for the annual values.",
        miss.length ? `Years with no value at all: ${years(miss)}.` : "No requested year was entirely missing.",
        e.seasonal ? coverageSentence(e) : e.observations.excluded.length ? `Years excluded by the coverage rules: ${years(e.observations.excluded.map((x) => x.year))}.` : "",
      ] },
      { kind: "background", lines: ["Missing data means the dataset had no valid observation (for example, clouds for satellite vegetation data, or a product not yet released). Years that do not meet the coverage rules are excluded rather than filled in, so gaps never become zeros."] },
      { kind: "limitations", lines: [e.seasonal ? `Only months with data in enough years are used: ${e.seasonal.months.join(", ") || "none"}.` : "", scopeLine(e)] },
    ], [analysisSource(e), datasetSource(e)], e);
  },

  provenance(e) {
    return answer("provenance", "supported", [
      { kind: "finding", lines: [
        `Dataset: ${e.dataset.source} — ${e.dataset.title ?? e.dataset.id}.`,
        `Version: ${e.dataset.version}. Type: ${e.dataset.provenance}.`,
        `Spatial footprint: ${e.footprint.description} (${e.footprint.resolution}).`,
        `Annual value: ${e.annualValueDefinition}.`,
        e.dataset.citation ? `Citation: ${e.dataset.citation}` : "",
        e.dataset.doi ? `DOI: ${e.dataset.doi}` : "The application's dataset catalog lists no DOI for this dataset, so no external link is shown.",
        `Data status: ${e.dataStatus.label}.`,
      ] },
    ], [datasetSource(e), guideSource], e);
  },

  dataset_choice(e, r) {
    const soil = e.variableId === "soil_moisture"
      ? ["GLDAS-2.1 Noah is a land-surface model estimate for a 0–10 cm layer, available from 2000. SMAP L3 Enhanced is a satellite retrieval for roughly the top 5 cm, available from 2015. They represent related but different quantities."]
      : [];
    return answer("dataset_choice", r?.comparison ? "supported" : "needs_analysis", [
      { kind: "finding", lines: [`This investigation uses ${e.dataset.source} (${e.dataset.id}), the dataset selected for ${lower(e.variableName)} in Explore Earth.`, ...soil] },
      { kind: "background", lines: ["No dataset is best everywhere. The right choice depends on the period you need, the spatial footprint, and whether you want a model, reanalysis or satellite estimate."] },
      r?.comparison
        ? { kind: "statistics", lines: [`Your Compare Datasets result for this place and period reports: ${r.comparison.agreementLabel ?? "no agreement level"}. ${r.comparison.explanation ?? r.comparison.unavailableReason ?? ""}`, "Agreement between datasets does not show which one is more accurate."] }
        : { kind: "next_steps", lines: [`To see whether alternative datasets agree here, run Compare Datasets for ${lower(e.variableName)} with the same place and period. Only one dataset was analysed in this investigation.`, regionNote(e)] },
    ], [datasetSource(e), { label: "Compare Datasets", detail: "Analyse several datasets side by side", href: "#compare" }], e);
  },

  dataset_disagreement(e, r) {
    const c = r?.comparison;
    if (!c) {
      return answer("dataset_disagreement", "needs_analysis", [
        { kind: "finding", lines: [`Only one dataset (${e.dataset.source}, ${e.dataset.id}) was analysed in this investigation, so it is not possible to say whether datasets disagree here.`, regionNote(e)] },
        { kind: "background", lines: ["In general, datasets can differ because they measure different quantities (for example, model layers versus satellite retrievals), cover different footprints, use different inputs and processing, or treat missing data differently."] },
        { kind: "next_steps", lines: [e.variableId === "soil_moisture" ? "Run the soil-moisture comparison in Scientific Evaluation, or Compare Datasets, for this place and period." : "Run Compare Datasets for this variable with the same place and period."] },
      ], [{ label: "Compare Datasets", detail: "Analyse several datasets side by side", href: "#compare" }], e);
    }
    return answer("dataset_disagreement", c.pairs.length ? "descriptive" : "not_answerable", [
      { kind: "finding", lines: [
        `Compare Datasets analysed ${c.datasets.length} datasets for this place and period: ${c.datasets.map((d) => `${d.name} (${d.outcome.replace(/_/g, " ")})`).join("; ")}.`,
        c.agreementLabel ? `Agreement level reported: ${c.agreementLabel}. ${c.explanation ?? ""}` : `No comparison was produced: ${c.unavailableReason ?? "reason not given"}.`,
        c.agreementLabel && c.directionEvidence !== "indicative" && !(c.explanation ?? "").includes("not an established")
          ? "Directions come from descriptive slopes over each pair's common eligible years, so this is not an established agreement or conflict."
          : "",
      ] },
      { kind: "statistics", lines: c.pairs.map((p) => `• ${p.names[0]} vs ${p.names[1]}: ${p.lineage.replace(/_/g, " ")}; ${p.commonYears} common eligible years; ${pairDirectionText(p.direction)}; ${p.numericallyComparable ? `Spearman ρ ${p.spearmanRho === null ? "unavailable" : num(p.spearmanRho)}` : `magnitudes not compared${p.notComparableReason ? ` (${p.notComparableReason})` : ""}`}.`) },
      { kind: "background", lines: [c.pairs.map((p) => p.lineageNote).filter(Boolean)[0] ?? "Datasets with shared inputs are not independent confirmations of each other."] },
      { kind: "limitations", lines: [c.independenceNote ?? "", c.comparabilityNote ?? "", c.caution ?? "", "Correlation describes association only; it does not show accuracy or causation.", "The datasets are analysed separately and never merged."] },
    ], [{ label: "Compare Datasets result", detail: "Cached result of your comparison for this place and period", href: "#compare" }, ...c.datasets.map((d) => ({ label: d.name, detail: [d.version && `Version: ${d.version}`, d.citation && `Citation: ${d.citation}`].filter(Boolean).join(" · ") || "Catalog entry" }))], e);
  },

  ols_vs_theil_sen(e) {
    const m = e.methodsLab;
    const background = "Theil–Sen takes the median of the slopes between every pair of eligible years, so a few unusual years have limited influence. OLS minimises squared errors, so individual values — especially at the ends of a record — can pull it more.";
    if (!m) {
      return answer("ols_vs_theil_sen", "not_answerable", [
        { kind: "background", lines: [background] },
        { kind: "notice", lines: ["This result does not include the Statistical Methods Lab comparison (for example, it may be a saved snapshot), so no OLS slope is available to compare."] },
      ], [methodsSource], e);
    }
    if (e.seasonal) {
      return answer("ols_vs_theil_sen", "descriptive", [
        { kind: "finding", lines: [`For NDVI the comparison is between the seasonal Sen slope (${signedNum(e.trend.slope)} ${e.units.slope ?? ""}) and a deseasonalized OLS slope (${signedNum(m.seasonalOls)}) on the same monthly observations. No annual OLS is fitted, because the seasonal method uses a different sample.`] },
        { kind: "background", lines: [background] },
        { kind: "limitations", lines: ["The OLS slope is descriptive only: no p-value or confidence interval is reported for it."] },
      ], [methodsSource, analysisSource(e)], e);
    }
    if (m.olsSlope === null) {
      return answer("ols_vs_theil_sen", "not_answerable", [
        { kind: "notice", lines: [`An OLS comparison is not available: ${m.unavailableReason ?? "reason not given"}.`] },
        { kind: "background", lines: [background] },
      ], [methodsSource], e);
    }
    return answer("ols_vs_theil_sen", "descriptive", [
      { kind: "finding", lines: [`On the same ${m.n ?? "eligible"} eligible years: Theil–Sen ${signedNum(m.theilSenSlope)} ${e.units.slope ?? ""}; OLS ${signedNum(m.olsSlope)} ${e.units.slope ?? ""}; OLS minus Theil–Sen ${signedNum(m.difference)} ${e.units.slope ?? ""}.`] },
      { kind: "uncertainty", lines: [ESTIMATOR_READING] },
      { kind: "background", lines: [background] },
      { kind: "limitations", lines: ["The OLS slope is descriptive only: no p-value or confidence interval is reported for it. The trend the application reports is Theil–Sen."] },
    ], [methodsSource, analysisSource(e)], e);
  },

  methodology(e) {
    return answer("methodology", "supported", [
      { kind: "finding", lines: e.seasonal
        ? [
          `NDVI uses the ${e.trend.test} test and the ${e.trend.estimator}. Monthly means are compared within the same calendar month across years, because cloud gaps leave too few complete years for an annual method.`,
          `Months used: ${e.seasonal.months.join(", ") || "none"}${e.seasonal.sampleCount !== null ? ` (${e.seasonal.sampleCount} monthly values)` : ""}.`,
        ]
        : [
          `Annual value: ${e.annualValueDefinition}.`,
          `Trend: the ${e.trend.estimator} (median of pairwise slopes between eligible years), with the ${e.trend.test} test for a monotonic trend.`,
          "Before a p-value is reported, a lag-1 serial-dependence screen checks whether neighbouring years are correlated; if they are, significance is withheld.",
          "A Pettitt change-point check flags abrupt shifts that a single straight line would misrepresent.",
        ] },
      { kind: "limitations", lines: ["Results are descriptive or indicative; the method summaries in Scientific Information list the assumptions."] },
    ], [analysisSource(e), methodsSource, guideSource], e);
  },

  seasonal_months(e) {
    if (!e.seasonal) {
      return answer("seasonal_months", "supported", [
        { kind: "finding", lines: [`This ${lower(e.variableName)} analysis uses annual values, not individual months. ${e.monthly ? `${e.monthly.valid} of ${e.monthly.expected} monthly values had valid data.` : ""}`] },
      ], [analysisSource(e)], e);
    }
    return answer("seasonal_months", "supported", [
      { kind: "finding", lines: [`Months that contributed: ${e.seasonal.months.join(", ") || "none"}${e.seasonal.sampleCount !== null ? `, giving ${e.seasonal.sampleCount} monthly values` : ""}.`, "A calendar month is used only if it has data in at least 70% of the years; other months are left out, not filled."] },
      { kind: "limitations", lines: ["The trend therefore describes these months only, not the whole year."] },
    ], [analysisSource(e), methodsSource], e);
  },

  autocorrelation(e) {
    const d = e.trend.dependence;
    return answer("autocorrelation", d ? "supported" : "not_answerable", [
      { kind: "statistics", lines: d
        ? [`Lag-1 dependence screen: ${d.status.replace(/_/g, " ")}${d.rho !== null ? ` (Spearman ρ = ${num(d.rho)})` : ""}.`, d.caveat, d.supportsInference ? "Standard significance testing was allowed." : "Standard significance testing was withheld."]
        : [`No serial-dependence result is available${e.seasonal ? " for the seasonal method" : ""}.`] },
      { kind: "background", lines: ["When consecutive years are correlated, there is less independent information than the number of years suggests, which makes standard p-values too small."] },
    ], [analysisSource(e), methodsSource], e);
  },

  change_point(e) {
    const cp = e.trend.changePoint;
    const lines = !cp
      ? ["No change-point result is available for this analysis."]
      : cp.status === "step_detected"
        ? [`An abrupt step was detected: the mean changed by ${signedNum(cp.shift ?? null)} ${e.units.annual} between ${cp.last_year_before} and ${cp.first_year_after}${cp.pettitt_p_value !== undefined ? ` (Pettitt ${pText(cp.pettitt_p_value)})` : ""}.`, "A step can reflect a real shift or a change in the data source; a single straight-line trend may misrepresent it."]
        : cp.status === "none"
          ? ["No abrupt step was detected in the eligible years."]
          : [`The change-point check was not run${cp.reason ? `: ${cp.reason}` : ""}.`];
    return answer("change_point", cp && cp.status !== "not_tested" ? "supported" : "not_answerable", [{ kind: "statistics", lines }], [analysisSource(e), methodsSource], e);
  },

  correlation(e, r) {
    const rel = r?.relationships ?? [];
    if (!rel.length) {
      return answer("correlation", "needs_analysis", [
        { kind: "notice", lines: [`No relationship analysis for ${lower(e.variableName)} at this place and period has been run in this session. Open Earth System Relationships and compare annual values with another variable.`, regionNote(e)] },
      ], [{ label: "Earth System Relationships", detail: "Compare annual values of two variables", href: "#relationships" }], e);
    }
    return answer("correlation", "descriptive", [
      { kind: "statistics", lines: rel.map((x) => `• With ${x.other.replace(/_/g, " ")}: Spearman ρ (annual values) ${x.rhoAnnual === null ? "unavailable" : num(x.rhoAnnual)}; ρ (year-to-year changes) ${x.rhoFirstDifferences === null ? "unavailable" : num(x.rhoFirstDifferences)}; ${x.commonYears.length} common eligible years.${x.unavailableReasons.length ? ` ${x.unavailableReasons.map(reasonLabel).join("; ")}` : ""}`) },
      { kind: "background", lines: rel.map((x) => x.interpretation).filter(Boolean) },
      { kind: "limitations", lines: ["Correlation is association, not causation. Short records give unstable correlations.", rel.some((x) => x.spatialSupportsDiffer) ? "The two variables come from different spatial footprints." : ""] },
    ], [{ label: "Earth System Relationships result", detail: "Cached result for this place and period", href: "#relationships" }], e);
  },
};
