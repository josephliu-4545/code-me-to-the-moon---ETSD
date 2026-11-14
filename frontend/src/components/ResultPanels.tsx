import { useEffect, useState } from "react";
import AccessKeyForm from "./AccessKeyForm";
import type { Analysis } from "../api/types";
import { ApiError, isUnreachable } from "../api/types";
import { dataStatusLabel, decadeUnits, fmt, fmtCoord, perDecade, pText, signed } from "../lib/format";
import { stepWarning, summarize } from "../lib/summary";
import { discoveryHeadline, inSentence, fittedChange, intervalReading, isSeasonal, monthCompleteness, monthsUsed, periodLabel, slopeName, testName, trendVerdict } from "../lib/verdict";
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

const pretty = (k: string) => k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

function Layer({ n, title, children, className = "" }: { n: number; title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`layer ${className}`} aria-labelledby={`layer-${n}`}>
      <h3 id={`layer-${n}`} className="layer-title"><span className="layer-num" aria-hidden>{String(n).padStart(2, "0")}</span>{title}</h3>
      {children}
    </section>
  );
}

/** Layers 1–3 of the discovery reveal: what we found, how much it changed, how strong the evidence is. */
export function ResultSummary({ analysis, place }: { analysis: Analysis; place?: string }) {
  const t = analysis.trend;
  const verdict = trendVerdict(analysis);
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
            <p className="kicker">Mission findings</p>
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
          <h2 id="finding-title" className="discovery-headline">{discoveryHeadline(analysis)}</h2>
          <div className="verdict-row">
            <span className={`verdict-pill verdict-${verdict.kind}`}><span className="verdict-mark" aria-hidden />{verdict.label}</span>
            <p className="finding-note">{verdict.note}</p>
          </div>
          {step && <p className="step-warning" role="note"><strong>Sudden step in the record.</strong> {step}</p>}
          <p className="support-note">
            Values describe a {inSentence(s.description)} ({s.resolution}), not the exact point. Source: {analysis.dataset.source} · {analysis.dataset.title ?? analysis.dataset.id}.
          </p>
        </div>
      </header>

      <div className="layers">
        <Layer n={2} title="How much did it change?" className="layer-change">
          <div className="change-grid">
            <div className="change-main">
              <span className="figure-label">{slopeName(analysis)}</span>
              <span className="figure-value mono">{t?.slope != null ? signed(t.slope, 4) : "—"}</span>
              <span className="figure-unit">{t?.slope != null ? slopeUnits : "No slope estimated"}</span>
            </div>
            {t?.slope != null && (
              <div className="change-side">
                <span className="figure-label">Per decade</span>
                <span className="change-value mono">{signed(perDecade(t.slope), 3)}</span>
                <span className="figure-unit">{decadeUnits(t.slope_units ?? null)}</span>
              </div>
            )}
            {change && (
              <div className="change-side">
                <span className="figure-label">Along the fitted line</span>
                <span className="change-value mono">{signed(change.value, 3)}</span>
                <span className="figure-unit">{analysis.units.annual_value} from {change.from} to {change.to}</span>
              </div>
            )}
          </div>
          {change && <p className="layer-note">The fitted-line change is slope × years between the first and last eligible years. It is not the observed difference between those two years’ values.</p>}
        </Layer>

        <Layer n={3} title="How strong is the evidence?" className="layer-evidence">
          <dl className="evidence">
            <div className="ev">
              <dt>Inference</dt>
              <dd>
                <span className={`ev-value level-${verdict.kind}`}>{verdict.inference}</span>
                <span className="ev-unit">{t?.mann_kendall ? `${testName(analysis)} ${pText(t.mann_kendall.p_value)} (α = ${t.mann_kendall.alpha})` : t?.result_level_label ?? ""}</span>
              </dd>
            </div>
            <div className="ev">
              <dt>95% slope interval</dt>
              <dd>
                {t?.confidence_interval ? (
                  <span className="ev-value mono ev-range">{signed(t.confidence_interval[0], 3)} … {signed(t.confidence_interval[1], 3)}</span>
                ) : (
                  <span className="ev-value ev-na">Not reported</span>
                )}
                <span className="ev-unit">{t?.confidence_interval ? slopeUnits : t?.confidence_interval_unavailable_reason ?? "Only reported with statistical inference"}</span>
                {t?.slope != null && t.confidence_interval && <CiRuler slope={t.slope} ci={t.confidence_interval} units={slopeUnits} compact />}
              </dd>
            </div>
            {seasonal ? (
              <div className="ev">
                <dt>Monthly values used</dt>
                <dd>
                  <span className="ev-value mono">{t?.sample_count ?? 0}</span>
                  <span className="ev-unit">{monthsUsed(analysis) || "no calendar month qualified"}</span>
                </dd>
              </div>
            ) : (
              <div className="ev">
                <dt>Eligible years</dt>
                <dd>
                  <span className="ev-value mono">{analysis.coverage.eligible_years}/{analysis.coverage.years_requested}</span>
                  <span className="ev-unit">complete-data years</span>
                  <YearStrip annual={analysis.annual} units={analysis.units.annual_value} />
                </dd>
              </div>
            )}
            {months.expected > 0 ? (
              <div className="ev">
                <dt>Monthly completeness</dt>
                <dd>
                  <span className="ev-value mono">{Math.round((months.valid / months.expected) * 100)}%</span>
                  <span className="ev-unit">{months.valid} of {months.expected} months valid</span>
                  <span className="ev-meter" aria-hidden><span style={{ width: `${(months.valid / months.expected) * 100}%` }} /></span>
                </dd>
              </div>
            ) : sd ? (
              <div className="ev">
                <dt>Year-to-year dependence</dt>
                <dd>
                  <span className="ev-value mono">{sd.lag1_spearman_rho === null ? "—" : fmt(sd.lag1_spearman_rho, 2)}</span>
                  <span className="ev-unit">lag-1 residual ρ · {sd.status.replace(/_/g, " ")}</span>
                </dd>
              </div>
            ) : null}
          </dl>
          {reading && <p className="layer-note">{reading}</p>}
          <ul className="summary-lines">
            {lines.map((l) => <li key={l}>{l}</li>)}
          </ul>
        </Layer>
      </div>
    </section>
  );
}

/** Layer 5: what the result does not support. Built from the result and the backend's own caveats. */
export function Cautions({ analysis }: { analysis: Analysis }) {
  const v = trendVerdict(analysis);
  const s = analysis.spatial_support;
  const excluded = analysis.coverage.years_requested - analysis.coverage.eligible_years;
  const items: { title: string; body: string }[] = [
    { title: "A trend is not a cause.", body: analysis.caveats[1] ?? "The slope describes change over the eligible years only. It is not a forecast and does not identify a cause." },
  ];
  if (v.kind === "not_detected") items.push({ title: "“No trend detected” is not “no change”.", body: "The test could not distinguish a monotonic trend from year-to-year variability. The data are consistent with no trend, and also with a modest trend this record is too short or noisy to detect." });
  if (v.kind === "increasing" || v.kind === "decreasing") items.push({ title: "Significant is indicative, not certain.", body: analysis.caveats[0] ?? "Autocorrelated years can inflate false positives." });
  if (v.kind === "descriptive") items.push({ title: "No significance test was reported.", body: analysis.trend?.significance_unavailable_reason ?? "The slope is a description of the eligible years, not a tested trend." });
  if (v.kind === "unavailable") items.push({ title: "Absence of a result is not absence of change.", body: "Too few years met the completeness rules to estimate a slope. Annual values remain visible as description." });
  items.push({ title: "This is an area, not an address.", body: `Values represent a ${inSentence(s.description)} (${s.resolution}). Local conditions at a specific site can differ.` });
  items.push({ title: "Know what kind of data this is.", body: `${analysis.dataset.source}: ${analysis.dataset.provenance.replace(/_/g, " ")}. Model estimates and satellite retrievals are not ground-station measurements.` });
  const step = stepWarning(analysis);
  if (step) items.push({ title: "A sudden step is not a gradual trend.", body: step });
  if (isSeasonal(analysis) && analysis.trend?.slope != null) items.push({ title: "Only some months are used.", body: `The trend compares ${monthsUsed(analysis)} with the same months in other years. The other months had too little usable data, so the result says nothing about them.` });
  if (excluded > 0 && !isSeasonal(analysis)) items.push({ title: "Not every year counted.", body: `${excluded} of ${analysis.coverage.years_requested} requested years were excluded by the completeness rules and are shown only as context.` });
  return (
    <section className="cautions" aria-labelledby="layer-5">
      <h3 id="layer-5" className="layer-title"><span className="layer-num" aria-hidden>05</span>What should you not conclude?</h3>
      <ul className="caution-list">
        {items.map((i) => <li key={i.title}><strong>{i.title}</strong> {i.body}</li>)}
      </ul>
    </section>
  );
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

export function MethodNotes({ analysis }: { analysis: Analysis }) {
  const tm = analysis.methodology.trend_method ?? {};
  const src = analysis.methodology.source;
  const srcEntries = src && typeof src === "object" ? Object.entries(src as Record<string, unknown>).filter(([, v]) => typeof v === "string") : [];
  return (
    <Disclosure summary="Methods and caveats" meta={`${Object.keys(tm).length + srcEntries.length} notes`}>
      <dl className="method-grid">
        {srcEntries.map(([k, v]) => (<div className="method-item" key={`s-${k}`}><dt>{pretty(k)}</dt><dd>{String(v)}</dd></div>))}
        {Object.entries(tm).map(([k, v]) => (<div className="method-item" key={k}><dt>{pretty(k)}</dt><dd>{v}</dd></div>))}
      </dl>
      {analysis.caveats.length > 1 && <div className="method-caveats"><p className="trace-label">Additional scientific notes</p>{analysis.caveats.slice(1).map((c) => <p key={c}>{c}</p>)}</div>}
    </Disclosure>
  );
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
