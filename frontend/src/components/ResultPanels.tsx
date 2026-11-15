import { useEffect, useState } from "react";
import AccessKeyForm from "./AccessKeyForm";
import type { Analysis } from "../api/types";
import { ApiError, isUnreachable } from "../api/types";
import { dataStatusLabel, decadeUnits, fmt, fmtCoord, perDecade, signed } from "../lib/format";
import { stepWarning, summarize } from "../lib/summary";
import { discoveryHeadline, inSentence, fittedChange, intervalReading, isSeasonal, monthCompleteness, monthsUsed, periodLabel, slopeName, trendVerdict } from "../lib/verdict";
import { headlineParts, plainReason, type StageId } from "../lib/evidence";
import MethodExplorer from "./expedition/MethodExplorer";
import ScientificGuardrails from "./expedition/ScientificGuardrails";
import { buildRows } from "./TrendChart";
import CiRuler from "./science/CiRuler";
import YearStrip from "./science/YearStrip";
import Disclosure from "./ui/Disclosure";
import VariableGlyph from "./ui/VariableGlyph";

export function DataStatusBadge({ analysis }: { analysis: Analysis }) {
  const s = dataStatusLabel(analysis);
  return (
    <span className={`badge badge-${s.tone}`}>
      <span className="badge-dot" aria-hidden />
      {s.label}
    </span>
  );
}


/** A compact sparkline of the real annual values and the backend's fitted line. Decorative twin of the full chart. */
function DiscoverySpark({ analysis }: { analysis: Analysis }) {
  const rows = buildRows(analysis);
  const vals = rows.flatMap((r) => [r.eligible, r.excluded, r.trend]).filter((v): v is number => v !== null);
  if (rows.length < 2 || !vals.length) return null;
  const lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1;
  const y0 = rows[0]!.year, y1 = rows[rows.length - 1]!.year;
  const x = (yr: number) => 8 + ((yr - y0) / Math.max(1, y1 - y0)) * 224;
  const y = (v: number) => 62 - ((v - lo) / span) * 52;
  const fitted = rows.filter((r) => r.trend !== null);
  return (
    <svg className="discovery-spark" viewBox="0 0 240 70" aria-hidden="true" focusable="false">
      <path d="M0 66h240" className="spark-ground" />
      {fitted.length > 1 && <path className="spark-trend" d={`M${x(fitted[0]!.year)} ${y(fitted[0]!.trend!)}L${x(fitted[fitted.length - 1]!.year)} ${y(fitted[fitted.length - 1]!.trend!)}`} />}
      {rows.map((r) => r.eligible !== null ? <circle key={r.year} cx={x(r.year)} cy={y(r.eligible)} r="3" className="spark-dot" /> : r.excluded !== null ? <circle key={r.year} cx={x(r.year)} cy={y(r.excluded)} r="3" className="spark-ring" /> : <path key={r.year} d={`M${x(r.year)} 60v6`} className="spark-gap" />)}
    </svg>
  );
}

/**
 * Experience A: a discovery you can understand in seconds.
 * Level 1 shows the short headline, its qualification and three instrument readouts.
 * Level 3 (the full scientific statement) stays one click away.
 */
export function ResultSummary({ analysis, place }: { analysis: Analysis; place?: string }) {
  const t = analysis.trend;
  const verdict = trendVerdict(analysis);
  const head = headlineParts(analysis);
  const lines = summarize(analysis);
  const months = monthCompleteness(analysis);
  const change = fittedChange(analysis);
  const reading = intervalReading(analysis);
  const slopeUnits = t?.slope_units ?? analysis.units.slope;
  const s = analysis.spatial_support;
  const sd = t?.serial_dependence;
  const step = stepWarning(analysis);
  const seasonal = isSeasonal(analysis);
  return (
    <section className="discovery" aria-labelledby="finding-title">
      <header className="discovery-head">
        <div className="finding-hero-visual" aria-hidden="true">
          <div className="finding-image-glow" />
          <img className="finding-earth-art" src="/mission-earth-astronaut.png" alt="" />
          <span className="finding-visual-caption">A living planet, observed from orbit</span>
        </div>
        <div className="finding-hero-copy">
          <div className="finding-meta">
            <p className="kicker">Mission findings · what did we discover?</p>
            <DataStatusBadge analysis={analysis} />
          </div>
          <p className="finding-context">
            <VariableGlyph id={analysis.variable.id} size={18} />
            <span>{analysis.variable.name}</span>
            <span className="sep" aria-hidden>·</span>
            <span>{place || fmtCoord(s.requested.latitude, s.requested.longitude)}</span>
            <span className="sep" aria-hidden>·</span>
            <span className="mono">{periodLabel(analysis)}</span>
          </p>
          <h2 id="finding-title" className="discovery-headline">{head.headline}</h2>
          <p className={`discovery-qualifier qualifier-${head.kind}`}>{head.qualifier}</p>
          <div className="verdict-row">
            <span className={`verdict-pill verdict-${verdict.kind}`}><span className="verdict-mark" aria-hidden />{verdict.label}</span>
          </div>
          {step && <p className="step-warning" role="note"><strong>Sudden step in the record.</strong> {step}</p>}
        </div>
      </header>

      <div className="readout-deck" aria-label="Key results">
        <div className="readout readout-rate">
          <span className="readout-q">How much did it change?</span>
          <span className="figure-label">{slopeName(analysis)}</span>
          <span className="figure-value mono">{t?.slope != null ? signed(t.slope, 4) : "—"}</span>
          <span className="figure-unit">{t?.slope != null ? slopeUnits : plainReason(t?.slope_unavailable_reason) ?? "No slope estimated"}</span>
          {t?.slope != null && <span className="readout-sub mono">{signed(perDecade(t.slope), 3)} {decadeUnits(t.slope_units ?? null)}</span>}
          <DiscoverySpark analysis={analysis} />
        </div>
        <div className={`readout readout-evidence level-${verdict.kind}`}>
          <span className="readout-q">How reliable is the evidence?</span>
          <span className="figure-label">Significance</span>
          <span className={`ev-value level-${verdict.kind}`}>{head.significance}</span>
          <span className="ev-unit">{head.significanceDetail}</span>
          {t?.slope != null && t.confidence_interval
            ? <CiRuler slope={t.slope} ci={t.confidence_interval} units={slopeUnits} compact />
            : <span className="ev-unit readout-na">95% interval: {t?.confidence_interval_unavailable_reason ? "not reported" : "only reported with a supported test"}</span>}
        </div>
        {seasonal ? (
          <div className="readout readout-years">
            <span className="readout-q">How much data?</span>
            <span className="figure-label">Monthly values used</span>
            <span className="ev-value mono">{t?.sample_count ?? 0}</span>
            <span className="ev-unit">{monthsUsed(analysis) || "no calendar month qualified"}</span>
          </div>
        ) : (
          <div className="readout readout-years">
            <span className="readout-q">How much data?</span>
            <span className="figure-label">Eligible years</span>
            <span className="ev-value mono">{analysis.coverage.eligible_years}/{analysis.coverage.years_requested}</span>
            <span className="ev-unit">complete-data years</span>
            <YearStrip annual={analysis.annual} units={analysis.units.annual_value} />
          </div>
        )}
      </div>

      <Disclosure summary="Full scientific statement" meta="Technical" className="statement">
        <p className="statement-lead">{discoveryHeadline(analysis)} <span className="statement-note">{verdict.note}</span></p>
        <ul className="summary-lines">
          {lines.map((l) => <li key={l}>{l}</li>)}
        </ul>
        <dl className="statement-facts">
          <div><dt>Reported test</dt><dd>{t?.mann_kendall ? `Kendall: p = ${fmt(t.mann_kendall.p_value, 4)}, alpha = ${t.mann_kendall.alpha}` : `Test not reported: ${t?.significance_unavailable_reason ?? "Inference unavailable"}`}</dd></div>
          {t?.slope != null && <div><dt>Per decade</dt><dd className="mono">{signed(perDecade(t.slope), 3)} {decadeUnits(t.slope_units ?? null)}</dd></div>}
          {change && <div><dt>Along the fitted line</dt><dd><span className="mono">{signed(change.value, 3)}</span> {analysis.units.annual_value} from {change.from} to {change.to}</dd></div>}
          <div><dt>Inference</dt><dd>{verdict.inference} · {t?.result_level_label ?? "No trend computed"}</dd></div>
          {t?.confidence_interval && <div><dt>95% slope interval</dt><dd className="mono">{signed(t.confidence_interval[0], 3)} … {signed(t.confidence_interval[1], 3)} {slopeUnits}</dd></div>}
          {months.expected > 0 && <div><dt>Monthly completeness</dt><dd>{months.valid} of {months.expected} months valid ({Math.round((months.valid / months.expected) * 100)}%)</dd></div>}
          {sd && <div><dt>Year-to-year dependence</dt><dd>lag-1 residual ρ {sd.lag1_spearman_rho === null ? "—" : fmt(sd.lag1_spearman_rho, 2)} · {sd.status.replace(/_/g, " ")}</dd></div>}
        </dl>
        {change && <p className="layer-note">The fitted-line change is slope × years between the first and last eligible years. It is not the observed difference between those two years’ values.</p>}
        {reading && <p className="layer-note">{reading}</p>}
        {t?.confidence_interval && <p className="layer-note">This is not a prediction interval. It describes uncertainty in the estimated slope under the reported method and assumptions.</p>}
        <p className="support-note">Values describe a {inSentence(s.description)} ({s.resolution}), not the exact point. Source: {analysis.dataset.source} · {analysis.dataset.title ?? analysis.dataset.id}.</p>
        <a className="text-link" href="#history">Explore the supporting observations</a>
      </Disclosure>
    </section>
  );
}

/** Experience C (kept under its original name for existing callers). */
export function Cautions({ analysis, onShowEvidence }: { analysis: Analysis; onShowEvidence?: (stage: StageId) => void }) {
  return <ScientificGuardrails analysis={analysis} onShowEvidence={onShowEvidence} />;
}

export function ProvenanceCard({ analysis }: { analysis: Analysis }) {
  const d = analysis.dataset;
  const s = analysis.spatial_support;
  return (
    <section className="provenance source-journey" aria-labelledby="prov-title">
      <header className="trace-heading">
        <div><p className="kicker">Follow the evidence</p><h3 id="prov-title">Data provenance</h3></div>
        <p>Every finding has a starting point. Trace this one from its source to the value you see.</p>
      </header>
      <div className="trace-stations">
        <article className="trace-station trace-source">
          <span className="trace-stop"><span aria-hidden>01</span> The source</span>
          <svg className="trace-satellite" viewBox="0 0 280 150" aria-hidden="true">
            <ellipse cx="140" cy="77" rx="115" ry="48" transform="rotate(-18 140 77)" fill="none" stroke="currentColor" strokeDasharray="2 7" opacity=".4" />
            <g transform="translate(140 75) rotate(-22)">
              <path d="M-100-21h65v42h-65zM35-21h65v42H35z" fill="rgba(88,120,167,.22)" stroke="currentColor" />
              <path d="M-80-21v42m20-42v42M55-21v42m20-42v42M-100 0h65M35 0h65M-35 0h70" fill="none" stroke="currentColor" opacity=".6" />
              <path d="M-24-25h48v50h-48z" fill="#202A3D" stroke="#CDD5E1" /><circle r="12" fill="#082A46" stroke="#80e3ef" />
              <path d="M0-25v-17m-15 0q15-18 30 0z" fill="none" stroke="#CDD5E1" />
            </g>
          </svg>
          <p className="trace-provider">{d.source}</p>
          <h4>{d.title ?? d.id}</h4>
          <p className="trace-type">{d.provenance.replace(/_/g, " ")}</p>
          <p className="trace-secondary">{d.version}</p>
          <small className="trace-art-note">Decorative spacecraft illustration</small>
        </article>
        <article className="trace-station trace-location">
          <span className="trace-stop"><span aria-hidden>02</span> The sampled area</span>
          <div className="trace-footprint" aria-hidden="true"><i /><i /><i /><i /><span /></div>
          <p className="trace-art-note">Sampling concept · not to scale</p>
          <h4>{s.resolution}</h4>
          <p>{s.description}</p>
          <dl className="trace-facts">
            <div><dt>Requested point</dt><dd className="mono">{fmtCoord(s.requested.latitude, s.requested.longitude)}</dd></div>
            {s.cell && <div><dt>Cell centre</dt><dd className="mono">{fmtCoord(s.cell.center[0], s.cell.center[1])}{s.cell.approximate ? " (approximate footprint)" : ""}</dd></div>}
            {s.bbox && <div><dt>Region box</dt><dd>W {s.bbox.west}°, S {s.bbox.south}°, E {s.bbox.east}°, N {s.bbox.north}°{s.region_area_km2 ? ` · ${Math.round(s.region_area_km2).toLocaleString()} km²` : ""}</dd></div>}
            {s.months_meeting_area_threshold !== undefined && <div><dt>Area coverage</dt><dd>{s.months_meeting_area_threshold} months met the {Math.round((s.min_valid_area_fraction ?? 0) * 100)}% valid-area rule</dd></div>}
          </dl>
          {s.cell_status && s.cell_status !== "ok" && <p className="trace-alert">Cell status: {s.cell_status.replace(/_/g, " ")}</p>}
          {s.coastal_proximity && <p className="trace-alert">Near water or a mask edge; no substitution</p>}
        </article>
        <article className="trace-station trace-measure">
          <span className="trace-stop"><span aria-hidden>03</span> The measurement</span>
          <VariableGlyph id={analysis.variable.id} size={58} />
          <h4>{analysis.variable.name}</h4>
          <p>{analysis.variable.annual_value_definition}</p>
          <dl className="trace-facts">
            <div><dt>Annual units</dt><dd>{analysis.units.annual_value}</dd></div>
            <div><dt>Slope units</dt><dd>{analysis.units.slope}</dd></div>
            {d.depth && <div><dt>Depth</dt><dd>{d.depth.top_cm}–{d.depth.bottom_cm} cm ({d.depth.semantics.replace(/_/g, " ")})</dd></div>}
          </dl>
        </article>
      </div>
      <footer className="trace-receipt">
        <div><span className="trace-label">Reference</span>{d.doi ? <a href={`https://doi.org/${d.doi}`} target="_blank" rel="noreferrer">DOI {d.doi} ↗</a> : <span>No DOI supplied by this dataset</span>}{d.citation && <p>{d.citation}</p>}</div>
        {analysis.cache && <div><span className="trace-label">Retrieved</span><time dateTime={analysis.cache.retrieved_at}>{new Date(analysis.cache.retrieved_at).toLocaleString()}</time></div>}
      </footer>
    </section>
  );
}

/** Methodology explorer (kept under its original name for existing callers). */
export function MethodNotes({ analysis }: { analysis: Analysis }) {
  return <MethodExplorer analysis={analysis} />;
}

export function Loading({ label }: { label: string }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const t = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="status-box status-loading" role="status" aria-live="polite">
      <span className="orbit-loader" aria-hidden><span /></span>
      <div>
        <strong>{label}</strong>
        <p className="status-hint">
          <span className="mono">{elapsed}s</span> elapsed. Earth Engine retrievals can take 10–60 seconds; NASA POWER is usually faster. You can keep exploring—results appear when ready.
        </p>
      </div>
    </div>
  );
}

export function ErrorBox({ error, onRetry, extra }: { error: unknown; onRetry?: () => void; extra?: React.ReactNode }) {
  const e = error instanceof ApiError ? error : null;
  let title = "Something went wrong";
  let hint = e?.message ?? String(error);
  if (isUnreachable(e)) {
    title = "Analysis service not reachable";
  } else if (e?.status === 422) {
    title = e.reason === "outside_dataset_coverage" || e.reason === "unsupported_land_cover_region" ? "Not available at this location" : "This request is not supported";
  } else if (e?.status === 401) {
    title = "Team access key required";
  } else if (e?.status === 409 && e.reason === "analysis_changed") {
    title = "Investigation evidence changed";
  } else if (e?.status === 429) {
    title = "Please slow down";
  } else if (e?.status === 504) {
    title = "The NASA data request timed out";
    hint = "Try a shorter period or retry; cached results will be reused.";
  } else if (e?.status === 503) {
    title = "Data service busy or unavailable";
  } else if (e?.status === 502) {
    title = "NASA data retrieval failed";
  }
  return (
    <div className="status-box status-error" role="alert">
      <span className="status-icon" aria-hidden>!</span>
      <div>
        <strong>{title}</strong>
        <p className="status-hint">{hint}</p>
        <div className="row-gap">
          {onRetry && e?.status !== 422 && <button type="button" className="btn btn-ghost" onClick={onRetry}>Retry</button>}
          {extra}
        </div>
        {e?.status === 401 && e.reason === "api_key_required" && <AccessKeyForm />}
      </div>
    </div>
  );
}

export function Limitations({ analysis }: { analysis: Analysis }) {
  return (
    <Disclosure summary="Limitations" meta={analysis.limitations.length}>
      <ul className="limitations">
        {analysis.limitations.map((l) => <li key={l}>{l}</li>)}
      </ul>
    </Disclosure>
  );
}
