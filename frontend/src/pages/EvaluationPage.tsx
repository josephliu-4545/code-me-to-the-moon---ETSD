import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AnalysisRequest, AnnualPoint } from "../api/types";
import { SOIL_DATASETS } from "../components/AnalysisControls";
import { DataStatusBadge, ErrorBox, Limitations, Loading } from "../components/ResultPanels";
import CiRuler from "../components/science/CiRuler";
import EvidenceChain from "../components/science/EvidenceChain";
import MonthMatrix from "../components/science/MonthMatrix";
import YearStrip from "../components/science/YearStrip";
import MethodsLab from "../components/methodslab/MethodsLab";
import Disclosure from "../components/ui/Disclosure";
import EmptyState from "../components/ui/EmptyState";
import PageHero from "../components/ui/PageHero";
import VariableGlyph from "../components/ui/VariableGlyph";
import { fmt, fmtCoord, pText, reasonLabel, signed } from "../lib/format";
import { stepWarning } from "../lib/summary";
import { intervalReading, isSeasonal, monthCompleteness, monthsUsed, periodLabel, slopeName, testName, trendVerdict } from "../lib/verdict";
import { useAnalysis } from "../state/useAnalysis";

/** Years sharing the same exclusion reasons are listed together, so repeated reasons do not dominate the page. */
function groupExclusions(years: AnnualPoint[]): { years: number[]; reasons: string }[] {
  const groups = new Map<string, number[]>();
  for (const y of years) {
    const r = y.reasons.length ? y.reasons.map(reasonLabel).join("; ") : "No annual value";
    groups.set(r, [...(groups.get(r) ?? []), y.year]);
  }
  return [...groups.entries()].map(([reasons, ys]) => ({ reasons, years: ys }));
}

/** Plain-language meaning of the backend's result level. */
function levelExplanation(level: string | undefined): string {
  if (level === "statistical_inference") return "Inferential: a significance test was run, so the result can be read as evidence for or against a monotonic trend — with the caveats below.";
  if (level === "descriptive_slope") return "Descriptive: a slope was estimated, but too few eligible years (or a dependence screen) prevented a significance test.";
  return "Description only: too few eligible years to estimate a slope. Annual values are still shown.";
}

function Gauge({ label, value, total, hint }: { label: string; value: number; total: number; hint: string }) {
  const pct = total ? Math.round((value / total) * 100) : 0;
  return (
    <div className="gauge">
      <div className="gauge-head"><span>{label}</span><strong className="mono">{value}/{total}</strong></div>
      <div className="gauge-bar" role="meter" aria-valuemin={0} aria-valuemax={total} aria-valuenow={value} aria-label={label}>
        <span style={{ width: `${pct}%` }} />
      </div>
      <p className="gauge-hint">{hint}</p>
    </div>
  );
}

function SoilMoistureComparison({ request }: { request: AnalysisRequest }) {
  const [pair, setPair] = useState<string[]>(["gldas_2_1_noah_0_10cm", "smap_l3e_v006_am"]);
  const [run, setRun] = useState(false);
  const q = useQuery({
    queryKey: ["sm-compare", pair, request.latitude, request.longitude, request.startYear, request.endYear],
    queryFn: ({ signal }) => api.soilMoistureCompare(pair, request.latitude, request.longitude, request.startYear, request.endYear, signal),
    enabled: run,
  });
  const label = (k: string) => SOIL_DATASETS.find((d) => d.key === k)?.label ?? k;
  const agree = q.data?.descriptive_agreement.slope_sign_agreement;
  return (
    <section className="lab-section" aria-labelledby="cmp-h">
      <div className="lab-section-head">
        <p className="kicker">04 · Dataset comparison</p>
        <h2 id="cmp-h" className="section-title">Two soil-moisture records, side by side</h2>
        <p className="section-lede">Each dataset is analysed on its own and they are never merged. Differences in depth, footprint and method mean they measure related but different quantities — which is why two products can disagree without either being wrong.</p>
      </div>
      <div className="compare-controls">
        {[0, 1].map((i) => (
          <label className="field" key={i}>
            <span className="field-label">{i === 0 ? "First" : "Second"}</span>
            <select value={pair[i]} onChange={(e) => { const p = [...pair]; p[i] = e.target.value; setPair(p); setRun(false); }}>
              {SOIL_DATASETS.map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
            </select>
          </label>
        ))}
        <button type="button" className="btn btn-ink" disabled={pair[0] === pair[1]} onClick={() => setRun(true)}>Compare datasets</button>
      </div>
      {q.isFetching && <Loading label="Retrieving both datasets…" />}
      {q.isError && <ErrorBox error={q.error} onRetry={() => q.refetch()} />}
      {q.data && !q.isFetching && (
        <div className="compare-result reveal">
          <div className="compare-pair">
            {Object.entries(q.data.results).map(([k, r]) => (
              <div className="compare-side" key={k}>
                <p className="compare-name">{label(k)}</p>
                <p className="compare-slope mono">{r.trend.theil_sen ? signed(r.trend.theil_sen.slope, 4) : "—"}</p>
                <p className="compare-unit">{r.trend.theil_sen ? r.trend.theil_sen.slope_units : "No slope"} · {r.trend.result_level.replace(/_/g, " ")}</p>
              </div>
            ))}
            <div className={`compare-agree ${agree === true ? "is-yes" : agree === false ? "is-no" : ""}`}>
              <span className="compare-agree-label">Slope signs agree</span>
              <strong>{agree === null || agree === undefined ? "not assessable" : agree ? "yes" : "no"}</strong>
              <span className="compare-agree-note">Units differ, so slopes are compared by sign only.</span>
            </div>
          </div>
          <ul className="bullets">{q.data.differences.map((d) => <li key={d}>{d}</li>)}</ul>
          {q.data.descriptive_agreement.pairs.map((p) => (
            <dl className="kv" key={p.datasets.join()}>
              <dt>Common valid months</dt><dd className="mono">{p.common_valid_months}</dd>
              <dt>Mean difference</dt><dd>{p.mean_difference_m3_m3 === null ? "—" : <span className="mono">{signed(p.mean_difference_m3_m3, 4)} m³ m⁻³</span>} <span className="muted">({p.mean_difference_label})</span></dd>
              <dt>Monthly anomaly ρ</dt><dd>{p.monthly_anomaly_spearman_rho === null ? `withheld (${p.unavailable_reasons.map(reasonLabel).join(", ")})` : <span className="mono">{fmt(p.monthly_anomaly_spearman_rho, 3)}</span>}</dd>
            </dl>
          ))}
          <p className="note">Common eligible years: <span className="mono">{q.data.common_eligible_years.join(", ") || "none"}</span> · Frozen GLDAS months excluded: <span className="mono">{q.data.descriptive_agreement.excluded_frozen_months}</span></p>
          <p className="caveat">{q.data.interpretation}</p>
          <Disclosure summary="Comparison table">
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th scope="col">Dataset</th><th scope="col">Trend level</th><th scope="col">Slope</th></tr></thead>
                <tbody>
                  {Object.entries(q.data.results).map(([k, r]) => (
                    <tr key={k}><td>{label(k)}</td><td>{r.trend.result_level.replace(/_/g, " ")}</td><td className="mono">{r.trend.theil_sen ? `${signed(r.trend.theil_sen.slope, 4)} ${r.trend.theil_sen.slope_units}` : "—"}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Disclosure>
        </div>
      )}
    </section>
  );
}

const LabArt = () => (
  <svg viewBox="0 0 160 120" width="160" height="120" fill="none">
    {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((i) => (
      <rect key={i} x={8 + i * 14.5} y={20} width={10} height={10} rx={2} className={i === 3 || i === 7 ? "art-off" : "art-on"} />
    ))}
    {[0, 1, 2, 3].map((r) => [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11].map((c) => (
      <rect key={`${r}-${c}`} x={8 + c * 12} y={46 + r * 12} width={9} height={9} rx={1.5} className={(r * 7 + c) % 11 === 3 ? "art-off" : "art-on art-soft"} />
    )))}
    <path d="M8 110h144" className="art-line" />
    <circle cx="96" cy="110" r="4" className="art-dot" />
  </svg>
);

export default function EvaluationPage({ submitted }: { submitted: AnalysisRequest | null }) {
  const query = useAnalysis(submitted);
  const [view, setView] = useState<"evaluation" | "lab">("evaluation");
  if (!submitted)
    return (
      <div className="page page-control">
        <PageHero kicker="Mission Control · Scientific Evaluation" title={<>How trustworthy is <em>this finding</em>?</>} tone="control">
          <p>Mission Control opens the evidence behind a trend: which years qualified, which months were missing, how wide the uncertainty is, and how the statistics were computed.</p>
        </PageHero>
        <div className="page-body">
          <EmptyState title="Run an analysis in Explore Earth first." art={<LabArt />} action={<a className="btn btn-ink" href="#explore">Go to Explore Earth →</a>}>
            <p>Nothing is shown here until a real NASA retrieval has been analysed. The lab never displays example or simulated results.</p>
          </EmptyState>
        </div>
      </div>
    );
  if (query.isFetching) return <div className="page page-control page-status"><Loading label="Waiting for the analysis…" /></div>;
  if (query.isError) return <div className="page page-control page-status"><ErrorBox error={query.error} onRetry={() => query.refetch()} /></div>;
  const a = query.data;
  if (!a) return null;
  const t = a.trend;
  const sd = t?.serial_dependence;
  const seasonal = isSeasonal(a);
  const step = stepWarning(a);
  const verdict = trendVerdict(a);
  const { valid: months, expected: expectedMonths } = monthCompleteness(a);
  const excluded = a.annual.filter((y) => !y.eligible);
  const slopeUnits = t?.slope_units ?? a.units.slope;
  return (
    <div className="page page-control evaluation">
      <PageHero
        kicker="Mission Control · Scientific Evaluation"
        tone="control"
        title={<><span className="title-line">Evidence review</span><em className="title-line">{a.variable.name}</em></>}
        aside={<DataStatusBadge analysis={a} />}
      >
        <p className="hero-context">
          <VariableGlyph id={a.variable.id} size={18} />
          <span className="mono">{fmtCoord(a.spatial_support.requested.latitude, a.spatial_support.requested.longitude)}</span>
          <span aria-hidden>·</span>
          <span className="mono">{periodLabel(a)}</span>
          <span aria-hidden>·</span>
          <span>{a.dataset.source}</span>
        </p>
        <p><strong className={`verdict-inline verdict-${verdict.kind}`}>{verdict.label}.</strong> {t?.result_level_label ?? "No trend result was returned."}</p>
        <p className="hero-plain">{levelExplanation(t?.result_level)}</p>
      </PageHero>

      <div className="page-body lab">
        <div className="eval-views" role="group" aria-label="Evaluation view">
          <button type="button" aria-pressed={view === "evaluation"} className={view === "evaluation" ? "active" : ""} onClick={() => setView("evaluation")}>Scientific Evaluation</button>
          <button type="button" aria-pressed={view === "lab"} className={view === "lab" ? "active" : ""} onClick={() => setView("lab")}>Statistical Methods Lab</button>
        </div>
        {view === "lab" ? <MethodsLab analysis={a} /> : (<>
        <section className="lab-section" aria-labelledby="chain-h">
          <div className="lab-section-head">
            <p className="kicker">00 · Evidence chain</p>
            <h2 id="chain-h" className="section-title">From satellite or model to finding</h2>
            <p className="section-lede">Each link is taken from the analysis response. A finding is only as strong as its weakest link.</p>
          </div>
          <EvidenceChain analysis={a} />
        </section>

        <section className="lab-section" aria-labelledby="elig-h">
          <div className="lab-section-head">
            <p className="kicker">01 · Eligibility</p>
            <h2 id="elig-h" className="section-title">Which years count</h2>
            <p className="section-lede">A year counts only if it meets the completeness rules for this variable — for example enough valid months spread across the year. Excluded years stay visible as context but never influence the slope.</p>
          </div>
          <div className="gauges">
            <Gauge label="Eligible years" value={a.coverage.eligible_years} total={a.coverage.years_requested} hint={seasonal ? `Not used for this trend: it compares monthly values (${t?.sample_count ?? 0} from ${monthsUsed(a) || "no qualifying month"}) instead of complete years.` : "Years meeting the completeness rules used for the trend."} />
            {expectedMonths > 0 && <Gauge label="Months with valid data" value={months} total={expectedMonths} hint="Across all requested years; missing months are never filled." />}
          </div>
          <div className="strip-large">
            <YearStrip annual={a.annual} units={a.units.annual_value} />
            <ul className="legend legend-inline" aria-hidden>
              <li><span className="key key-sq key-eligible" />Eligible</li>
              <li><span className="key key-sq key-excluded" />Excluded</li>
              <li><span className="key key-sq key-empty" />No value</li>
            </ul>
          </div>
          {excluded.length > 0 && (
            <ul className="exclusions">
              {groupExclusions(excluded).map((g) => (
                <li key={g.years.join()}><span className="mono">{g.years.join(", ")}</span>{g.reasons}</li>
              ))}
            </ul>
          )}
        </section>

        {expectedMonths > 0 && (
          <section className="lab-section" aria-labelledby="comp-h">
            <div className="lab-section-head">
              <p className="kicker">02 · Completeness</p>
              <h2 id="comp-h" className="section-title">Valid and missing months</h2>
              <p className="section-lede">Each square is one calendar month. Missing months are never interpolated or filled from another dataset.</p>
            </div>
            <MonthMatrix annual={a.annual} />
            <ul className="legend legend-inline" aria-hidden>
              <li><span className="key key-sq key-eligible" />Valid</li>
              <li><span className="key key-sq key-missing" />Missing</li>
              <li><span className="key key-sq key-empty" />Not reported</li>
            </ul>
          </section>
        )}

        <section className="lab-section" aria-labelledby="unc-h">
          <div className="lab-section-head">
            <p className="kicker">03 · Uncertainty</p>
            <h2 id="unc-h" className="section-title">How sure is the slope?</h2>
            <p className="section-lede">The {slopeName(a)} with its 95% interval, on a ruler centred on zero change.</p>
          </div>
          <div className="uncertainty">
            <div className="unc-figure">
              <span className="figure-label">{slopeName(a)}</span>
              {t?.slope != null ? (
                <>
                  <span className="figure-value mono">{signed(t.slope, 4)}</span>
                  <span className="figure-unit">{slopeUnits}</span>
                </>
              ) : (
                <span className="unc-na">Trend unavailable</span>
              )}
            </div>
            {t?.slope != null ? <CiRuler slope={t.slope} ci={t?.confidence_interval ?? null} units={slopeUnits} unavailableReason={t.confidence_interval_unavailable_reason} /> : <p className="ruler-empty">{t?.slope_unavailable_reason ?? "No slope was estimated, so there is no interval to show."}</p>}
          </div>
          <dl className="kv">
            <dt>Result level</dt><dd>{t?.result_level_label ?? "—"}</dd>
            <dt>Slope</dt><dd>{a.methodology.trend_method.slope}</dd>
            <dt>Confidence interval</dt><dd>{t?.confidence_interval ? <span className="mono">{signed(t.confidence_interval[0], 4)} to {signed(t.confidence_interval[1], 4)} {t.slope_units}</span> : t?.confidence_interval_unavailable_reason ?? "Not reported"}</dd>
            <dt>Significance</dt><dd>{t?.mann_kendall ? <span className="mono">{testName(a)} S = {t.mann_kendall.s}, τ = {fmt(t.mann_kendall.tau, 3)}, {pText(t.mann_kendall.p_value)}</span> : t?.significance_unavailable_reason ?? "Not reported"}</dd>
            <dt>Dependence screen</dt><dd>{a.methodology.trend_method.serial_dependence_screen ?? a.methodology.trend_method.not_applied ?? "Not reported"}</dd>
            {sd && (<><dt>Lag-1 residual correlation</dt><dd><span className="mono">{sd.lag1_spearman_rho === null ? "—" : fmt(sd.lag1_spearman_rho, 2)}</span> · {sd.status.replace(/_/g, " ")}. {sd.unavailable_reason ?? ""}</dd></>)}
          </dl>
          {intervalReading(a) && <p className="plain">{intervalReading(a)}</p>}
          {step && <p className="step-warning" role="note"><strong>Sudden step in the record.</strong> {step}</p>}
          <p className="plain">{seasonal
            ? "This variable uses the Seasonal Kendall test on monthly values: cloud or data gaps leave too few complete years for the annual method (Theil–Sen with a screened Mann–Kendall test) used for the other variables. Comparisons between the two methods are not available here."
            : "Only one trend method (Theil–Sen with a screened Mann–Kendall test) is computed for this variable; comparisons with other methods are not available, so this page cannot show whether another method would change the interpretation."}</p>
          {a.caveats[0] && <p className="caveat">{a.caveats[0]}</p>}
          {a.caveats[1] && <p className="note">{a.caveats[1]}</p>}
        </section>

        {a.variable.id === "soil_moisture" && <SoilMoistureComparison request={submitted} />}

        <section className="lab-section" aria-labelledby="ev-h">
          <div className="lab-section-head">
            <p className="kicker">Evidence</p>
            <h2 id="ev-h" className="section-title">Full record</h2>
          </div>
          <Disclosure summary="Year-by-year eligibility table" meta={`${a.annual.length} years`}>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th scope="col">Year</th><th scope="col">Annual value ({a.units.annual_value})</th><th scope="col">Coverage</th><th scope="col">Missing months</th><th scope="col">Status</th></tr></thead>
                <tbody>
                  {a.annual.map((y) => (
                    <tr key={y.year} className={y.eligible ? "" : "row-excluded"}>
                      <th scope="row" className="mono">{y.year}</th>
                      <td className="mono">{fmt(y.value, 3)}</td>
                      <td className="mono">{y.coverage_percentage === null ? "—" : `${fmt(y.coverage_percentage, 1)}%`}</td>
                      <td className="mono">{y.missing_months?.length ? y.missing_months.join(", ") : y.missing_months ? "none" : "—"}</td>
                      <td>{y.eligible ? <span className="ok-text">Eligible</span> : y.reasons.map(reasonLabel).join("; ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Disclosure>
          <Limitations analysis={a} />
        </section>
        </>)}
      </div>
    </div>
  );
}
