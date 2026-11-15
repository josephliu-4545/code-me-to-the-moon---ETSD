import { useId } from "react";
import type { Analysis } from "../../api/types";
import { decadeUnits, fmtCoord, perDecade, pText, signed } from "../../lib/format";
import { methodTopics, observationCounts, plainDependence, plainReason, plainYearReason, provenanceKind, reasonTally, stages, type StageId } from "../../lib/evidence";
import { calendarSeries } from "../../lib/series";
import { fittedChange, intervalReading, isSeasonal, monthsUsed, slopeName, testName, trendVerdict } from "../../lib/verdict";
import CiRuler from "../science/CiRuler";
import CompletenessTimeline from "./CompletenessTimeline";
import EvidencePlot from "./EvidencePlot";
import { StageGlyph } from "./Glyphs";

export type LabId = "trend" | "memory";

interface Props {
  analysis: Analysis;
  stage: StageId;
  onStage: (s: StageId) => void;
  focusYear: number | null;
  onFocusYear: (y: number) => void;
  onOpenLab: (lab: LabId) => void;
}

function DatasetPanel({ analysis: a }: { analysis: Analysis }) {
  const kind = provenanceKind(a);
  const s = a.spatial_support;
  return (
    <div className="sp-grid">
      <div className="sp-visual sp-visual-dataset"><StageGlyph id="dataset" kind={kind} /></div>
      <div>
        <p className="sp-lead">{kind === "model" ? "A computer model of Earth’s land and atmosphere, constrained by observations." : kind === "satellite" ? "Measured from orbit by a satellite instrument, then processed into a gridded product." : "A NASA data product."}</p>
        <dl className="sp-facts">
          <div><dt>Source</dt><dd>{a.dataset.source}</dd></div>
          <div><dt>Product</dt><dd>{a.dataset.title ?? a.dataset.id}</dd></div>
          <div><dt>Version</dt><dd>{a.dataset.version}</dd></div>
          <div><dt>Kind of data</dt><dd>{a.dataset.provenance.replace(/_/g, " ")}</dd></div>
          <div><dt>Footprint</dt><dd>{s.resolution}</dd></div>
          <div><dt>Requested point</dt><dd className="mono">{fmtCoord(s.requested.latitude, s.requested.longitude)}</dd></div>
        </dl>
      </div>
    </div>
  );
}

function ObservationsPanel({ analysis: a }: { analysis: Analysis }) {
  const counts = observationCounts(a);
  if (!counts) {
    const n = a.annual.filter((y) => y.value !== null).length;
    return (
      <div className="sp-stack">
        <p className="sp-lead">This product returns one value per year. The daily records behind them are summarised by the backend, so no monthly series is shown.</p>
        <p className="sp-big"><span className="mono">{n}</span> annual values returned for {a.annual.length} requested years</p>
      </div>
    );
  }
  const rows = calendarSeries(a.series, a.period.start, a.period.end_exclusive);
  return (
    <div className="sp-stack">
      <p className="sp-lead">{a.series_definition ? `Each mark is one ${a.series_definition.replace(/\.$/, "")}.` : "Each mark is one month in the returned series."} Gaps stay gaps; nothing is filled in.</p>
      <div className="obs-strip" role="img" aria-label={`${counts.valid} months with values, ${counts.withheld} months withheld by quality rules, ${counts.notReturned} months not returned, out of ${counts.total}`}>
        {rows.map((r) => <i key={r.month} className={`obs obs-${r.state}`} title={`${r.month}: ${r.state.replace("_", " ")}`} />)}
      </div>
      <ul className="obs-legend">
        <li><i className="obs obs-valid" /> <span className="mono">{counts.valid}</span> with values</li>
        <li><i className="obs obs-withheld" /> <span className="mono">{counts.withheld}</span> withheld by quality rules</li>
        <li><i className="obs obs-not_returned" /> <span className="mono">{counts.notReturned}</span> not returned</li>
      </ul>
    </div>
  );
}

function ScreeningPanel({ analysis: a }: { analysis: Analysis }) {
  const tally = reasonTally(a);
  const total = a.annual.length;
  const passed = a.annual.filter((y) => y.eligible).length;
  const rules = methodTopics(a).find((t) => t.id === "selected");
  return (
    <div className="sp-stack">
      <div className="funnel" role="img" aria-label={`${total} years requested, ${passed} passed the completeness rules`}>
        <span className="funnel-bar" style={{ width: "100%" }}><b className="mono">{total}</b> requested</span>
        <span className="funnel-bar funnel-pass" style={{ width: `${Math.max(passed / Math.max(total, 1), 0.08) * 100}%` }}><b className="mono">{passed}</b> passed</span>
      </div>
      {isSeasonal(a) && <p className="sp-lead">For this product the trend uses monthly values instead: calendar months with enough data across years ({monthsUsed(a) || "none qualified"}).</p>}
      {tally.length > 0 ? (
        <ul className="reason-tally">
          {tally.map((r) => <li key={r.code}><span className="rt-count mono">{r.years}</span><span>{plainYearReason(r.code)}</span></li>)}
        </ul>
      ) : <p className="sp-lead">No year was set aside.</p>}
      {rules && rules.facts.length > 0 ? (
        <ul className="methods-facts">{rules.facts.map((f) => <li key={f} className="mono">{f}</li>)}</ul>
      ) : <p className="sp-muted">The backend did not expose numeric screening thresholds for this product.</p>}
    </div>
  );
}

function TrendPanel({ analysis: a, focusYear, onFocusYear, onOpenLab }: Pick<Props, "analysis" | "focusYear" | "onFocusYear" | "onOpenLab">) {
  const t = a.trend;
  const change = fittedChange(a);
  if (t?.slope == null) {
    return (
      <div className="sp-stack">
        <p className="sp-lead">No trend line was estimated. {plainReason(t?.slope_unavailable_reason) ?? "Too little data passed the completeness rules."}</p>
        <EvidencePlot analysis={a} focusYear={focusYear} onSelectYear={onFocusYear} />
      </div>
    );
  }
  return (
    <div className="sp-grid sp-grid-wide">
      <EvidencePlot analysis={a} focusYear={focusYear} onSelectYear={onFocusYear} emphasis="trend" />
      <div className="sp-stack">
        <dl className="sp-facts">
          <div><dt>{slopeName(a)}</dt><dd><span className="mono">{signed(t.slope, 4)}</span> {t.slope_units ?? a.units.slope}</dd></div>
          <div><dt>Per decade</dt><dd><span className="mono">{signed(perDecade(t.slope), 3)}</span> {decadeUnits(t.slope_units ?? null)}</dd></div>
          {change && <div><dt>Along the fitted line</dt><dd><span className="mono">{signed(change.value, 3)}</span> {a.units.annual_value}, {change.from}–{change.to}</dd></div>}
        </dl>
        <p className="sp-muted">{isSeasonal(a)
          ? `This slope comes from qualifying monthly values (${monthsUsed(a) || "no qualifying months"}), compared month by month, so no line is drawn through these annual means.`
          : "Filled dots shaped the line; hollow rings were shown but not used."}</p>
        <button type="button" className="btn btn-ghost" onClick={() => onOpenLab("trend")}>How is this line found? →</button>
      </div>
    </div>
  );
}

function FindingPanel({ analysis: a, onOpenLab }: Pick<Props, "analysis" | "onOpenLab">) {
  const t = a.trend;
  const v = trendVerdict(a);
  const mk = t?.mann_kendall;
  const dep = plainDependence(t?.serial_dependence);
  const reading = intervalReading(a);
  const checks: { k: string; state: "pass" | "warn" | "off"; v: string; d: string }[] = [
    {
      k: "Direction",
      state: t?.slope == null ? "off" : "pass",
      v: t?.slope == null ? "No slope" : t.slope > 0 ? "Upward slope" : t.slope < 0 ? "Downward slope" : "Flat",
      d: t?.slope == null ? plainReason(t?.slope_unavailable_reason) ?? "Not enough eligible data." : "From the robust trend line.",
    },
    {
      k: "Year-to-year memory",
      state: dep.tone === "caution" ? "warn" : dep.tone === "ok" ? "pass" : "off",
      v: dep.tone === "caution" ? "Related years" : dep.tone === "ok" ? "Not detected" : "Not checked",
      d: dep.headline,
    },
    {
      k: "Significance",
      state: mk ? (mk.is_statistically_significant ? "pass" : "warn") : "off",
      v: mk ? (mk.is_statistically_significant ? "Significant (indicative)" : "Not significant") : "Not evaluated / reported",
      d: mk
        ? `${testName(a)} ${pText(mk.p_value)} at α = ${mk.alpha}.`
        : t?.significance_unavailable_reason && t.significance_unavailable_reason === t.serial_dependence?.unavailable_reason
          ? "The test was not run: the year-to-year memory screen blocked it."
          : plainReason(t?.significance_unavailable_reason) ?? "No test was run.",
    },
    {
      k: "Uncertainty range",
      state: t?.confidence_interval ? (reading?.includes("includes zero") ? "warn" : "pass") : "off",
      v: t?.confidence_interval ? (reading?.includes("includes zero") ? "Includes zero" : "Excludes zero") : "Not reported",
      d: t?.confidence_interval ? reading ?? "" : plainReason(t?.confidence_interval_unavailable_reason) ?? "Only reported alongside a supported test.",
    },
  ];
  return (
    <div className="sp-stack">
      <ol className="finding-chain">
        {checks.map((c) => (
          <li key={c.k} className={`fc fc-${c.state}`}>
            <span className="fc-mark" aria-hidden="true" />
            <span className="fc-k">{c.k}</span>
            <span className="fc-v">{c.v}</span>
            <span className="fc-d">{c.d}</span>
          </li>
        ))}
        <li className={`fc fc-verdict verdict-${v.kind}`}>
          <span className="fc-mark" aria-hidden="true" />
          <span className="fc-k">Therefore</span>
          <span className="fc-v">{v.label}</span>
          <span className="fc-d">{v.note}</span>
        </li>
      </ol>
      {t?.slope != null && t.confidence_interval && <CiRuler slope={t.slope} ci={t.confidence_interval} units={t.slope_units ?? a.units.slope} />}
      <button type="button" className="btn btn-ghost" onClick={() => onOpenLab("memory")}>Why does year-to-year memory matter? →</button>
    </div>
  );
}

/** B1: NASA Dataset → Observations → Quality Screening → Eligible Years → Trend → Scientific Finding. */
export default function EvidenceJourney({ analysis, stage, onStage, focusYear, onFocusYear, onOpenLab }: Props) {
  const list = stages(analysis);
  const base = useId();
  const kind = provenanceKind(analysis);
  const current = list.find((s) => s.id === stage)!;
  const index = list.indexOf(current);
  return (
    <div className="journey">
      <svg className="journey-orbit" viewBox="0 0 1200 120" preserveAspectRatio="none" aria-hidden="true">
        <path d="M20 96C300 10 900 10 1180 96" className="jo-path" />
        <path d="M20 96C300 10 900 10 1180 96" className="jo-progress" style={{ strokeDashoffset: `${100 - (index / (list.length - 1)) * 100}` }} pathLength={100} />
      </svg>
      <ol className="journey-stages" aria-label="Evidence journey">
        {list.map((s, i) => (
          <li key={s.id} className={`js js-${s.status} ${s.id === stage ? "is-active" : ""} ${i <= index ? "is-reached" : ""}`}>
            <button type="button" className="js-btn" aria-pressed={s.id === stage} aria-controls={`${base}-panel`} onClick={() => onStage(s.id)}>
              <span className="js-node"><StageGlyph id={s.id} kind={kind} /></span>
              <span className="js-num mono" aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
              <span className="js-label">{s.label}</span>
              <span className="js-readout">{s.readout}</span>
              <span className="sr-only">, status: {s.status === "ok" ? "complete" : s.status === "limited" ? "limited" : "unavailable"}</span>
            </button>
          </li>
        ))}
      </ol>
      <section id={`${base}-panel`} className={`stage-panel sp-${stage}`} aria-live="polite" aria-labelledby={`${base}-panel-title`}>
        <header className="sp-head">
          <span className="sp-num mono" aria-hidden="true">{String(index + 1).padStart(2, "0")} / {String(list.length).padStart(2, "0")}</span>
          <h4 id={`${base}-panel-title`} className="sp-title">{current.label}</h4>
          <p className="sp-question">{current.question}</p>
        </header>
        {stage === "dataset" && <DatasetPanel analysis={analysis} />}
        {stage === "observations" && <ObservationsPanel analysis={analysis} />}
        {stage === "screening" && <ScreeningPanel analysis={analysis} />}
        {stage === "eligible" && <CompletenessTimeline analysis={analysis} focusYear={focusYear} onSelectYear={onFocusYear} />}
        {stage === "trend" && <TrendPanel analysis={analysis} focusYear={focusYear} onFocusYear={onFocusYear} onOpenLab={onOpenLab} />}
        {stage === "finding" && <FindingPanel analysis={analysis} onOpenLab={onOpenLab} />}
        <nav className="sp-nav" aria-label="Move along the evidence journey">
          <button type="button" className="sp-step" disabled={index === 0} onClick={() => onStage(list[index - 1]!.id)}>← {index > 0 ? list[index - 1]!.label : "Start"}</button>
          <button type="button" className="sp-step" disabled={index === list.length - 1} onClick={() => onStage(list[index + 1]!.id)}>{index < list.length - 1 ? list[index + 1]!.label : "End"} →</button>
        </nav>
      </section>
    </div>
  );
}
