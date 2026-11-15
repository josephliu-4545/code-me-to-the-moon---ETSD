import type { Analysis, AnnualPoint, SerialDependence } from "../api/types";
import { fmt, pText, reasonLabel, signed } from "./format";
import { calendarSeries } from "./series";
import { stepWarning } from "./summary";
import { inSentence, isSeasonal, monthsUsed, periodLabel, testName, trendVerdict, type VerdictKind } from "./verdict";

/**
 * View models for the Earth Evidence Expedition.
 *
 * Everything here reshapes values the backend already returned. Nothing computes a new
 * statistic on the real observations, invents an exclusion reason or fills a missing month.
 * When the backend does not expose a detail, the model says so explicitly.
 */

export const MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

const pretty = (k: string) => k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

/* ------------------------------------------------------------------ */
/* Plain-language translations                                         */
/* ------------------------------------------------------------------ */

const PLAIN_REASONS: Record<string, string> = {
  "Material lag-1 serial dependence detected": "Some years may be related to earlier years, making the usual significance test unreliable.",
  "Inferential confidence interval not supported": "An uncertainty range is only reported when the significance test can be trusted.",
  "At least 3 eligible annual observations are required": "At least 3 complete years are needed before a slope can be estimated.",
  "At least 8 eligible annual observations are required": "At least 8 complete years are needed before a significance test is run.",
};

/** A friendlier sentence for a backend reason string; the original stays available as technical text. */
export function plainReason(reason: string | null | undefined): string | null {
  if (!reason) return null;
  if (PLAIN_REASONS[reason]) return PLAIN_REASONS[reason];
  const m = /^At least (\d+) eligible annual observations are required/.exec(reason);
  if (m) return `At least ${m[1]} complete years are needed for this step.`;
  return reason;
}

const PLAIN_YEAR_REASONS: Record<string, string> = {
  partial_calendar_year: "The year is only partly inside the requested period.",
  no_valid_observations: "No usable measurements were returned for this year.",
  insufficient_represented_months: "Too few months had usable data.",
  insufficient_valid_slot_coverage: "Too many days or time steps were missing.",
  missing_calendar_quarter: "A whole three-month season had no data.",
  insufficient_valid_months: "Fewer than 12 months had usable values.",
  missing_monthly_value: "At least one monthly value is missing.",
  provisional_recent_product: "Recent data are provisional and may still be revised.",
  outside_availability: "The dataset does not cover this year.",
};

export const plainYearReason = (code: string) => PLAIN_YEAR_REASONS[code] ?? reasonLabel(code);

export type DependencePlain = { tone: "ok" | "caution" | "unknown"; headline: string; detail: string };

/** Translates the lag-1 serial-dependence screen into everyday words. */
export function plainDependence(sd: SerialDependence | null | undefined): DependencePlain {
  if (!sd) return { tone: "unknown", headline: "Year-to-year memory was not checked for this result.", detail: "The backend did not report a serial-dependence screen, usually because too few years were eligible." };
  if (sd.status === "material_dependence_detected" || sd.supported_for_standard_inference === false) {
    return {
      tone: "caution",
      headline: "Some years may be related to earlier years, making the usual significance test unreliable.",
      detail: sd.unavailable_reason ? `Backend screen: ${sd.unavailable_reason}.` : "The backend screen flagged dependence between neighbouring years.",
    };
  }
  if (sd.lag1_spearman_rho === null) return { tone: "unknown", headline: "Year-to-year memory could not be measured.", detail: sd.unavailable_reason ?? sd.caveat };
  return {
    tone: "ok",
    headline: "No strong link between neighbouring years was found.",
    detail: "That does not prove the years are independent: with short records this check has little power.",
  };
}

/* ------------------------------------------------------------------ */
/* Experience A — headline                                              */
/* ------------------------------------------------------------------ */

export interface Headline { kind: VerdictKind; headline: string; qualifier: string; significance: string; significanceDetail: string }

/**
 * Two-level discovery: a short headline plus the qualification that must travel with it.
 * The headline never states more certainty than the verdict allows.
 */
export function headlineParts(a: Analysis): Headline {
  const v = trendVerdict(a);
  const t = a.trend;
  const name = inSentence(a.variable.name);
  const slope = t?.slope ?? 0;
  const dir = slope > 0 ? "upward" : slope < 0 ? "downward" : null;
  const mk = t?.mann_kendall;
  const test = testName(a);
  switch (v.kind) {
    case "unavailable":
      return {
        kind: v.kind,
        headline: "There isn’t enough reliable data to determine a long-term trend.",
        qualifier: "That is not evidence of no change. The record is too incomplete to judge.",
        significance: "Not evaluated",
        significanceDetail: plainReason(t?.significance_unavailable_reason) ?? "No slope, so no test.",
      };
    case "increasing":
    case "decreasing":
      return {
        kind: v.kind,
        headline: `An ${v.kind === "increasing" ? "upward" : "downward"} trend in ${name}, supported by the trend test.`,
        qualifier: `Treat it as indicative, not certain: the test can over-report trends when neighbouring ${isSeasonal(a) ? "months" : "years"} are related.`,
        significance: "Significant*",
        significanceDetail: mk ? `${test} ${pText(mk.p_value)} (α = ${mk.alpha})` : "",
      };
    case "not_detected":
      return {
        kind: v.kind,
        headline: dir ? `${dir === "upward" ? "An upward" : "A downward"} slope in ${name}, but the evidence is inconclusive.` : `No monotonic trend detected in ${name}.`,
        qualifier: "The trend test could not tell this slope apart from year-to-year ups and downs. That is not proof of no change.",
        significance: "Not significant",
        significanceDetail: mk ? `${test} ${pText(mk.p_value)} (α = ${mk.alpha})` : "",
      };
    case "descriptive":
      return {
        kind: v.kind,
        headline: dir ? `${dir === "upward" ? "An upward" : "A downward"} estimated trend in ${name}.` : `A flat estimated trend in ${name}.`,
        qualifier: "This result is descriptive. A significance test was not reported.",
        significance: "Not evaluated",
        significanceDetail: plainReason(t?.significance_unavailable_reason) ?? "No significance test was reported.",
      };
  }
}

/* ------------------------------------------------------------------ */
/* Experience B — evidence journey                                      */
/* ------------------------------------------------------------------ */

export type StageId = "dataset" | "observations" | "screening" | "eligible" | "trend" | "finding";
export type StageStatus = "ok" | "limited" | "unavailable";

export interface Stage { id: StageId; label: string; question: string; readout: string; status: StageStatus }

export type ProvenanceKind = "model" | "satellite" | "other";
export function provenanceKind(a: Analysis): ProvenanceKind {
  const p = `${a.dataset.provenance} ${a.dataset.source}`.toLowerCase();
  if (/model|reanalysis|assimilat|land surface|noah|gldas/.test(p)) return "model";
  if (/satellite|retriev|remote|modis|imerg|smap|radiometer/.test(p)) return "satellite";
  return "other";
}

/** Monthly observation counts from the returned series; null when no monthly series was returned. */
export function observationCounts(a: Analysis): { valid: number; withheld: number; notReturned: number; total: number } | null {
  if (!a.series.length) return null;
  const rows = calendarSeries(a.series, a.period.start, a.period.end_exclusive);
  return {
    valid: rows.filter((r) => r.state === "valid").length,
    withheld: rows.filter((r) => r.state === "withheld").length,
    notReturned: rows.filter((r) => r.state === "not_returned").length,
    total: rows.length,
  };
}

export function stages(a: Analysis): Stage[] {
  const t = a.trend;
  const v = trendVerdict(a);
  const obs = observationCounts(a);
  const requested = a.coverage.years_requested;
  const eligible = a.coverage.eligible_years;
  const excluded = a.annual.filter((y) => !y.eligible).length;
  const seasonal = isSeasonal(a);
  const yearsWithValues = a.annual.filter((y) => y.value !== null).length;
  return [
    { id: "dataset", label: "NASA dataset", question: "Where do the numbers come from?", readout: a.dataset.source, status: "ok" },
    {
      id: "observations",
      label: "Observations",
      question: "What was actually measured or estimated?",
      readout: obs ? `${obs.valid} of ${obs.total} months` : `${yearsWithValues} annual values`,
      status: obs ? (obs.valid === 0 ? "unavailable" : obs.valid < obs.total ? "limited" : "ok") : yearsWithValues ? "ok" : "unavailable",
    },
    {
      id: "screening",
      label: "Quality screening",
      question: "Which years were complete enough?",
      readout: excluded ? `${excluded} year${excluded === 1 ? "" : "s"} set aside` : "All years passed",
      status: excluded === 0 ? "ok" : excluded === a.annual.length ? "unavailable" : "limited",
    },
    seasonal
      ? { id: "eligible", label: "Eligible data", question: "What went into the trend?", readout: `${t?.sample_count ?? 0} monthly values`, status: (t?.sample_count ?? 0) > 0 ? "ok" : "unavailable" }
      : { id: "eligible", label: "Eligible years", question: "What went into the trend?", readout: `${eligible} of ${requested} years`, status: eligible === 0 ? "unavailable" : eligible < requested ? "limited" : "ok" },
    {
      id: "trend",
      label: "Trend",
      question: "How fast did it change?",
      readout: t?.slope != null ? `${signed(t.slope, 3)} ${t.slope_units ?? a.units.slope}` : "Not estimated",
      status: t?.slope != null ? "ok" : "unavailable",
    },
    {
      id: "finding",
      label: "Scientific finding",
      question: "What can we conclude?",
      readout: v.label,
      status: v.kind === "increasing" || v.kind === "decreasing" ? "ok" : v.kind === "unavailable" ? "unavailable" : "limited",
    },
  ];
}

/* ------------------------------------------------------------------ */
/* B2 — year and month records                                          */
/* ------------------------------------------------------------------ */

export type MonthCell = "valid" | "missing" | "unknown";

export interface YearRecord {
  year: number;
  value: number | null;
  eligible: boolean;
  status: "eligible" | "excluded" | "empty";
  reasons: string[];
  months: MonthCell[];
  /** Where the month states came from; "none" means the backend reported no month detail. */
  monthSource: "annual" | "series" | "none";
  monthValues: (number | null)[];
  coverage: number | null;
  facts: [string, string][];
}

function factValue(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "number") return fmt(v, 3);
  if (typeof v === "string") return v;
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (Array.isArray(v) && v.every((x) => typeof x === "number")) return v.map((x) => fmt(x as number, 3)).join(" – ");
  return null;
}

export function yearRecords(a: Analysis): YearRecord[] {
  const byYear = new Map<number, Map<number, { value: number | null; valid: boolean }>>();
  for (const p of a.series) {
    const y = Number(p.date.slice(0, 4));
    const m = Number(p.date.slice(5, 7));
    if (!Number.isFinite(y) || !m) continue;
    const valid = p.usable !== false && p.value !== null && Number.isFinite(p.value);
    if (!byYear.has(y)) byYear.set(y, new Map());
    byYear.get(y)!.set(m, { value: valid ? p.value : null, valid });
  }
  return a.annual.map((y: AnnualPoint) => {
    const series = byYear.get(y.year);
    let months: MonthCell[];
    let monthSource: YearRecord["monthSource"];
    if (y.represented_months !== null) {
      monthSource = "annual";
      months = MONTH_ABBR.map((_, i) => (y.represented_months!.includes(i + 1) ? "valid" : y.missing_months?.includes(i + 1) ? "missing" : "unknown"));
    } else if (series) {
      monthSource = "series";
      months = MONTH_ABBR.map((_, i) => {
        const s = series.get(i + 1);
        return s ? (s.valid ? "valid" : "missing") : "unknown";
      });
    } else {
      monthSource = "none";
      months = MONTH_ABBR.map(() => "unknown");
    }
    const monthValues = MONTH_ABBR.map((_, i) => series?.get(i + 1)?.value ?? null);
    const facts = Object.entries(y.extra ?? {})
      .map(([k, v]) => [pretty(k), factValue(v)] as const)
      .filter((e): e is [string, string] => e[1] !== null);
    return {
      year: y.year,
      value: y.value,
      eligible: y.eligible,
      status: y.eligible ? "eligible" : y.value === null ? "empty" : "excluded",
      reasons: y.reasons,
      months,
      monthSource,
      monthValues,
      coverage: y.coverage_percentage,
      facts,
    };
  });
}

/** How many years were set aside for each backend reason code. */
export function reasonTally(a: Analysis): { code: string; years: number }[] {
  const m = new Map<string, number>();
  for (const y of a.annual) if (!y.eligible) for (const r of y.reasons) m.set(r, (m.get(r) ?? 0) + 1);
  return [...m.entries()].map(([code, years]) => ({ code, years })).sort((x, y) => y.years - x.years);
}

/* ------------------------------------------------------------------ */
/* B5 — methodology explorer                                           */
/* ------------------------------------------------------------------ */

export type TopicId = "derived" | "selected" | "trend" | "uncertainty" | "caveats";
export interface MethodNote { key: string; label: string; value: string; origin: "source" | "trend_method" | "extra" | "caveat" }
export interface Topic { id: TopicId; title: string; plain: string; notes: MethodNote[]; facts: string[] }

const TOPIC_RULES: [TopicId, RegExp][] = [
  ["caveats", /(inference_caveat|descriptive_slope_note|thresholds_are_universal|status$)/],
  ["uncertainty", /(significance|serial_dependence|confidence_interval|alpha|lag1|residual_pairs)/],
  ["trend", /(^|›\s*)(slope|trend_policy|minimum_slope_years)|trend_basis/],
  ["selected", /(minimum|require|exclude|support_policy|annual_policy|missing_values|provisional|min_|slot)/],
  ["derived", /(conversion|aggregation|trend_input|value_definition|percentile|window|quantile|comparison|leap|bootstrap|reference_period)/],
];

function topicFor(key: string): TopicId {
  for (const [id, re] of TOPIC_RULES) if (re.test(key)) return id;
  return "derived";
}

function flatten(obj: unknown, prefix: string, out: [string, string][]) {
  if (obj === null || obj === undefined) return;
  if (typeof obj !== "object" || Array.isArray(obj)) {
    out.push([prefix, Array.isArray(obj) ? JSON.stringify(obj) : String(obj)]);
    return;
  }
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) flatten(v, prefix ? `${prefix} › ${k}` : k, out);
}

const leaf = (k: string) => k.split(" › ").pop()!;

/** Every backend methodology note, grouped by topic. Values are kept verbatim; identical repeats appear once. */
export function methodNotes(a: Analysis): MethodNote[] {
  const seen = new Set<string>();
  const notes: MethodNote[] = [];
  const add = (key: string, value: string, origin: MethodNote["origin"]) => {
    const sig = `${leaf(key)}=${value}`;
    if (seen.has(sig) || seen.has(`=${value}`) && value.length > 60) return;
    seen.add(sig);
    if (value.length > 60) seen.add(`=${value}`);
    notes.push({ key, label: key.split(" › ").map(pretty).join(" › "), value, origin });
  };
  const tm: [string, string][] = [];
  flatten(a.methodology.trend_method ?? {}, "", tm);
  const src: [string, string][] = [];
  flatten(a.methodology.source ?? {}, "", src);
  for (const [k, v] of src) add(k, v, "source");
  for (const [k, v] of tm) add(k, v, "trend_method");
  // Extreme heat: the reference period lives in `extra`; keep it with the derivation notes.
  const ref = a.extra?.reference_period;
  if (ref && typeof ref === "object") {
    const r: [string, string][] = [];
    flatten(ref, "reference_period", r);
    for (const [k, v] of r) add(k, v, "extra");
  }
  if (typeof a.extra?.trend_basis === "string") add("trend_basis", a.extra.trend_basis, "extra");
  a.caveats.forEach((c, i) => add(`caveat_${i + 1}`, c, "caveat"));
  return notes;
}

const TOPIC_TITLES: Record<TopicId, string> = {
  derived: "How the measurements were derived",
  selected: "How usable observations were selected",
  trend: "How the trend was estimated",
  uncertainty: "How uncertainty and significance were assessed",
  caveats: "Important assumptions and caveats",
};

export function methodTopics(a: Analysis): Topic[] {
  const notes = methodNotes(a);
  const t = a.trend;
  const v = trendVerdict(a);
  const seasonal = isSeasonal(a);
  const plain: Record<TopicId, string> = {
    derived: `Each yearly number is the ${a.variable.annual_value_definition.replace(/\.$/, "")}.`,
    selected: seasonal
      ? `Calendar months with data in enough years were kept: ${monthsUsed(a) || "none qualified"}.`
      : `${a.coverage.eligible_years} of ${a.coverage.years_requested} years were complete enough to use. Gaps are never filled or treated as zero.`,
    trend: t?.slope != null
      ? `The slope is the median of the slopes between every pair of ${seasonal ? "same-month values" : "years"}, so one unusual year cannot drag it far.`
      : "No slope was estimated because too little data passed the completeness rules.",
    uncertainty: v.kind === "descriptive" || v.kind === "unavailable"
      ? "No significance test was reported for this result, so its reliability was not evaluated."
      : `A ${testName(a)} test checked whether the ups and downs could hide the slope.`,
    caveats: "Read these before quoting the result.",
  };
  return (Object.keys(TOPIC_TITLES) as TopicId[])
    .map((id) => {
      const own = notes.filter((n) => (n.origin === "caveat" ? "caveats" : topicFor(n.key)) === id);
      const facts = own.filter((n) => n.value.length <= 26 && n.origin !== "caveat").slice(0, 4).map((n) => `${pretty(leaf(n.key))}: ${n.value}`);
      return { id, title: TOPIC_TITLES[id], plain: plain[id], notes: own, facts };
    })
    .filter((tp) => tp.notes.length > 0 || tp.id === "trend" || tp.id === "uncertainty");
}

/* ------------------------------------------------------------------ */
/* Experience C — guardrails                                            */
/* ------------------------------------------------------------------ */

export type GuardVisual = "cause" | "area" | "inference" | "inconclusive" | "indicative" | "nochange" | "station" | "satellite" | "step" | "months" | "years" | "dataset";

export interface Guardrail { id: string; visual: GuardVisual; title: string; line: string; detail: string; relevance: string; notes: string[]; stage?: StageId }

const AREA_RE = /grid|pixel|cell|area|region|footprint|spatial/i;
const SOURCE_RE = /station|model|estimate|retriev|satellite|observation|reanalysis|in situ/i;

/** Only the limitations that apply to this dataset and this result. Each backend limitation appears once. */
export function guardrails(a: Analysis): Guardrail[] {
  const v = trendVerdict(a);
  const t = a.trend;
  const s = a.spatial_support;
  const tm = a.methodology.trend_method ?? {};
  const units = t?.slope_units ?? a.units.slope;
  const items: Guardrail[] = [];
  const remaining = [...a.limitations];
  const take = (re: RegExp) => {
    const hit = remaining.filter((l) => re.test(l));
    for (const h of hit) remaining.splice(remaining.indexOf(h), 1);
    return hit;
  };

  if (v.kind === "unavailable") {
    items.push({
      id: "nochange", visual: "nochange",
      title: "Absence of a result is not absence of change.",
      line: "Too little complete data means we cannot judge, not that nothing happened.",
      detail: "A trend needs enough complete years. When the record has too many gaps, the honest answer is “we don’t know yet”.",
      relevance: plainReason(t?.slope_unavailable_reason) ?? `Only ${a.coverage.eligible_years} of ${a.coverage.years_requested} years met the completeness rules.`,
      notes: [t?.slope_unavailable_reason].filter((x): x is string => !!x),
      stage: "eligible",
    });
  } else {
    items.push({
      id: "cause", visual: "cause",
      title: "A trend is not a cause.",
      line: "The slope shows how values changed, not why they changed.",
      detail: "Many things can move a signal at once: natural variability, land-use change, or changes in the data itself. A trend line summarises direction; finding the cause needs a separate attribution study.",
      relevance: `This slope (${signed(t?.slope ?? null, 4)} ${units}) describes ${periodLabel(a)} only. It is not a forecast.`,
      notes: [tm.descriptive_slope_note ?? a.caveats[1]].filter((x): x is string => !!x),
      stage: "trend",
    });
  }

  if (v.kind === "descriptive") {
    items.push({
      id: "inference", visual: "inference",
      title: "No significance test means no significance conclusion.",
      line: "We can describe the slope, but not say whether it is more than noise.",
      detail: "Without a test, “not significant” would be wrong too. The reliability of this slope was simply not evaluated.",
      relevance: plainReason(t?.significance_unavailable_reason) ?? "The backend did not report a significance test for this result.",
      notes: [t?.significance_unavailable_reason, t?.confidence_interval_unavailable_reason, t?.serial_dependence?.caveat].filter((x): x is string => !!x),
      stage: "finding",
    });
  } else if (v.kind === "not_detected") {
    items.push({
      id: "inference", visual: "inconclusive",
      title: "“No trend detected” is not “no change”.",
      line: "The test could not separate the slope from natural ups and downs.",
      detail: "The data are consistent with no trend, and also with a modest trend that this record is too short or noisy to detect.",
      relevance: t?.mann_kendall ? `${testName(a)} ${pText(t.mann_kendall.p_value)} at α = ${t.mann_kendall.alpha}.` : "The test did not reject “no monotonic trend”.",
      notes: [tm.inference_caveat ?? a.caveats[0]].filter((x): x is string => !!x),
      stage: "finding",
    });
  } else if (v.kind === "increasing" || v.kind === "decreasing") {
    items.push({
      id: "inference", visual: "indicative",
      title: "Significant is indicative, not certain.",
      line: "Related neighbouring years can make the test too confident.",
      detail: "The screened test can reject “no trend” more often than its nominal 5% when years are autocorrelated. Treat the result as a strong hint, not proof.",
      relevance: t?.mann_kendall ? `${testName(a)} ${pText(t.mann_kendall.p_value)} at α = ${t.mann_kendall.alpha}.` : "",
      notes: [tm.inference_caveat ?? a.caveats[0]].filter((x): x is string => !!x),
      stage: "finding",
    });
  }

  items.push({
    id: "area", visual: "area",
    title: "An area is not an address.",
    line: "The value describes a whole sampled area around your point.",
    detail: "Gridded and pixel products average conditions over an area. A street, a field or a rooftop inside it can be hotter, wetter or greener than the average.",
    relevance: `This result is a ${inSentence(s.description)} (${s.resolution}).`,
    notes: take(AREA_RE),
    stage: "dataset",
  });

  const kind = provenanceKind(a);
  items.push({
    id: "source",
    visual: kind === "satellite" ? "satellite" : "station",
    title: kind === "model" ? "Models are not ground stations." : kind === "satellite" ? "A satellite view is not a ground station." : "Know what kind of data this is.",
    line: kind === "model" ? "These values are model estimates, not instrument readings at a site." : kind === "satellite" ? "Satellites infer conditions from orbit; they do not touch the ground." : "Different sources measure in different ways.",
    detail: "Model estimates and satellite retrievals are checked against ground instruments, but they are not the same thing. Agreement between products is not the same as validated accuracy.",
    relevance: `${a.dataset.source}: ${a.dataset.provenance.replace(/_/g, " ")}.`,
    notes: take(SOURCE_RE),
    stage: "dataset",
  });

  const step = stepWarning(a);
  if (step) items.push({ id: "step", visual: "step", title: "A sudden step is not a gradual trend.", line: "One jump can masquerade as steady change.", detail: step, relevance: step, notes: [], stage: "trend" });
  if (isSeasonal(a) && t?.slope != null)
    items.push({ id: "months", visual: "months", title: "Only some months are used.", line: "The other months had too little usable data.", detail: `The trend compares ${monthsUsed(a)} with the same months in other years.`, relevance: "The result says nothing about the months that were left out.", notes: [], stage: "eligible" });
  const excluded = a.coverage.years_requested - a.coverage.eligible_years;
  if (excluded > 0 && !isSeasonal(a) && v.kind !== "unavailable")
    items.push({ id: "years", visual: "years", title: "Not every year counted.", line: `${excluded} of ${a.coverage.years_requested} years were set aside.`, detail: "Years that failed the completeness rules are shown for context only; they do not shape the trend.", relevance: `${excluded} requested year${excluded === 1 ? "" : "s"} excluded by the completeness rules.`, notes: [], stage: "eligible" });
  if (remaining.length)
    items.push({ id: "dataset", visual: "dataset", title: "What this dataset can’t tell you.", line: `${remaining.length} limit${remaining.length === 1 ? "" : "s"} stated by the data provider.`, detail: "These limits come with the dataset itself and apply to every result built from it.", relevance: "Stated for this product by the backend.", notes: remaining, stage: "dataset" });
  return items;
}
