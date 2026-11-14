import { useRef, useState, type KeyboardEvent } from "react";
import type { MethodsLab as Lab } from "../../api/methodsLabTypes";
import type { Analysis } from "../../api/types";
import { fmt, reasonLabel, signed } from "../../lib/format";
import MethodComparisonChart from "./MethodComparisonChart";
import OutlierExperiment from "./OutlierExperiment";
import "./methods-lab.css";

export const LAB_TABS = [
  { id: "overview", label: "Overview" },
  { id: "estimators", label: "OLS vs Theil–Sen" },
  { id: "significance", label: "Trend significance" },
  { id: "dependence", label: "Autocorrelation" },
  { id: "change", label: "Abrupt changes" },
  { id: "simulation", label: "Outlier experiment" },
  { id: "assumptions", label: "Assumptions" },
] as const;
type TabId = (typeof LAB_TABS)[number]["id"];

/**
 * Descriptive reading of the OLS–Theil–Sen difference. The Theil–Sen interval is an interval for the
 * Theil–Sen slope only, not for the difference between estimators, so it is never used to judge agreement,
 * and the difference is never attributed to particular years without evidence.
 */
export const ESTIMATOR_READING =
  "Both slopes are reported descriptively. No formal test of agreement between the estimators was performed: " +
  "the Theil–Sen 95% interval describes uncertainty in the Theil–Sen slope only, not in the difference between " +
  "the two estimators, and the difference is not attributed to particular years.";

function Unavailable({ children }: { children: React.ReactNode }) {
  return <p className="lab-unavailable" role="note"><strong>Not available:</strong> {children}</p>;
}

function Overview({ lab, a }: { lab: Lab; a: Analysis }) {
  const obs = lab.observations;
  return (
    <>
      <p className="section-lede">
        These are the statistics behind this investigation, computed by the backend from the same NASA observations shown in Scientific Evaluation. Switching tabs never re-downloads data.
      </p>
      <dl className="kv">
        <dt>Observations used</dt><dd>{obs.basis}</dd>
        {lab.applicable.annual_comparison && (<><dt>Eligible years</dt><dd className="mono">{obs.eligible.map((e) => e.year).join(", ") || "none"}</dd></>)}
        {lab.seasonal && (<><dt>Months used</dt><dd>{lab.seasonal.month_names_used.join(", ") || "none"} · {lab.seasonal.sample_count} monthly values from {lab.seasonal.years_contributing.length} years</dd></>)}
        <dt>Slope needs</dt><dd>at least {lab.requirements.minimum_years_for_slope} eligible years</dd>
        <dt>Significance needs</dt><dd>at least {lab.requirements.minimum_years_for_significance} eligible years, α = {lab.requirements.alpha}, and {lab.requirements.dependence_screen}</dd>
      </dl>
      {obs.excluded.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <caption className="note">Years left out of every fitted line, and why</caption>
            <thead><tr><th>Year</th><th>Value ({a.units.annual_value})</th><th>Reason</th></tr></thead>
            <tbody>
              {obs.excluded.map((x) => (
                <tr key={x.year}><td className="mono">{x.year}</td><td className="mono">{fmt(x.value, 3)}</td><td>{(x.reasons ?? []).map(reasonLabel).join("; ") || "—"}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ul className="method-cards">
        {Object.entries(lab.methods)
          .filter(([k]) => (lab.applicable.seasonal ? k !== "ols" : !["seasonal_kendall", "deseasonalized_ols"].includes(k)))
          .map(([k, m]) => (
            <li key={k} className="method-card"><strong>{m.name}</strong><p>{m.definition}</p><p className="note">{m.role}</p></li>
          ))}
      </ul>
      {!lab.applicable.seasonal && lab.seasonal_unavailable_reason && <p className="note">Seasonal methods: {lab.seasonal_unavailable_reason}</p>}
    </>
  );
}

function Estimators({ lab, a }: { lab: Lab; a: Analysis }) {
  if (lab.seasonal) {
    const s = lab.seasonal;
    return (
      <>
        <Unavailable>{lab.annual_comparison_unavailable_reason}</Unavailable>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Estimator (same monthly observations)</th><th>Slope</th><th>95% interval</th></tr></thead>
            <tbody>
              <tr><td>Seasonal Sen slope (the trend reported)</td><td className="mono">{s.seasonal_sen_slope == null ? "—" : `${signed(s.seasonal_sen_slope, 5)} ${s.slope_units ?? ""}`}</td><td>{s.confidence_interval ? <span className="mono">{signed(s.confidence_interval[0], 5)} to {signed(s.confidence_interval[1], 5)}</span> : s.confidence_interval_unavailable_reason ?? "not reported"}</td></tr>
              <tr><td>Deseasonalized OLS (descriptive)</td><td className="mono">{s.deseasonalized_ols_slope == null ? s.deseasonalized_ols_unavailable_reason : `${signed(s.deseasonalized_ols_slope, 5)} ${s.slope_units ?? ""}`}</td><td>not computed (descriptive only)</td></tr>
            </tbody>
          </table>
        </div>
        <p className="note">{s.comparison_note}</p>
        <p className="note">{s.availability_rule} Months not used: {s.months_not_used.length ? s.months_not_used.join(", ") : "none"}.</p>
      </>
    );
  }
  if (lab.unavailable) return <Unavailable>{lab.unavailable}</Unavailable>;
  const o = lab.ols!;
  const t = lab.theil_sen!;
  const c = lab.comparison;
  return (
    <>
      <div className="table-wrap">
        <table className="table" data-testid="estimator-table">
          <thead><tr><th>Estimator</th><th>Slope</th><th>Eligible years</th><th>Extra</th></tr></thead>
          <tbody>
            <tr>
              <td>Theil–Sen (the trend reported)</td>
              <td className="mono">{t.slope == null ? "—" : `${signed(t.slope, 4)} ${t.slope_units ?? ""}`}</td>
              <td className="mono">{t.n}</td>
              <td>{t.confidence_interval ? <>95% interval <span className="mono">{signed(t.confidence_interval[0], 4)} to {signed(t.confidence_interval[1], 4)}</span></> : (t.confidence_interval_unavailable_reason ?? t.unavailable_reason ?? "—")}</td>
            </tr>
            <tr>
              <td>OLS (descriptive only)</td>
              <td className="mono">{o.slope == null ? "—" : `${signed(o.slope, 4)} ${o.slope_units ?? ""}`}</td>
              <td className="mono">{o.n}</td>
              <td>{o.available ? (o.r_squared == null ? o.r_squared_unavailable_reason : <>R² <span className="mono">{fmt(o.r_squared, 3)}</span></>) : o.unavailable_reason}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {c ? (
        <>
          <p data-testid="slope-difference">
            OLS minus Theil–Sen: <strong className="mono">{signed(c.slope_difference, 4)} {c.slope_units}</strong> on the same {c.n} eligible years.{" "}
            {ESTIMATOR_READING}
          </p>
          <MethodComparisonChart lab={lab} units={a.units.annual_value} />
          <p className="note">{o.inference_note}</p>
        </>
      ) : (
        <Unavailable>{lab.comparison_unavailable_reason}</Unavailable>
      )}
    </>
  );
}

function Significance({ lab }: { lab: Lab }) {
  const mk = lab.seasonal ? lab.seasonal.seasonal_kendall : lab.mann_kendall;
  return (
    <>
      <p className="section-lede">
        {lab.seasonal ? "The Seasonal Kendall test" : "The Mann–Kendall test"} asks whether values tend to rise or fall consistently (a monotonic trend), without assuming a straight line.
      </p>
      {mk ? (
        <dl className="kv" data-testid="mk-results">
          <dt>S statistic</dt><dd className="mono">{mk.s}</dd>
          <dt>Kendall τ</dt><dd className="mono">{fmt(mk.tau, 3)}</dd>
          {mk.z != null && (<><dt>Z</dt><dd className="mono">{fmt(mk.z, 3)}</dd></>)}
          <dt>p-value</dt><dd className="mono">{fmt(mk.p_value, 4)}</dd>
          <dt>Threshold α</dt><dd className="mono">{mk.alpha}</dd>
          <dt>Result</dt><dd>{mk.is_statistically_significant ? `significant (${mk.direction}) — indicative` : "no monotonic trend detected at this threshold"}</dd>
        </dl>
      ) : (
        <Unavailable>{lab.significance_unavailable_reason ?? "No significance test was run for this result."}</Unavailable>
      )}
      <ul className="lab-points">
        <li>The p-value is the probability of seeing a pattern at least this strong <em>if there were no trend</em>. It is not the probability that there is no trend.</li>
        <li>A significant result is evidence of a consistent direction over these years. It does not show what caused it.</li>
        <li>A non-significant result does not prove there is no trend; short records and autocorrelation reduce the test's power.</li>
        <li>An independent Monte Carlo check found this screened test can exceed its nominal false-positive rate when years are autocorrelated, so results are labelled indicative.</li>
      </ul>
    </>
  );
}

function Dependence({ lab }: { lab: Lab }) {
  const sd = lab.serial_dependence;
  return (
    <>
      <p className="section-lede">
        Neighbouring years are often alike (autocorrelation). That makes ordinary significance tests too optimistic, so the project checks consecutive Theil–Sen residuals before reporting significance.
      </p>
      {sd ? (
        <dl className="kv" data-testid="dependence-results">
          <dt>Adjacent residual pairs</dt><dd className="mono">{sd.adjacent_pair_count}</dd>
          <dt>Lag-1 Spearman ρ</dt><dd className="mono">{fmt(sd.lag1_spearman_rho, 3)}</dd>
          <dt>Diagnostic p-value</dt><dd className="mono">{sd.diagnostic_p_value == null ? "—" : fmt(sd.diagnostic_p_value, 3)}</dd>
          <dt>Status</dt><dd>{sd.status.replace(/_/g, " ")}</dd>
          <dt>Standard inference supported</dt><dd>{sd.supported_for_standard_inference ? "yes" : `no — ${sd.unavailable_reason ?? "see status"}`}</dd>
        </dl>
      ) : (
        <Unavailable>{lab.seasonal ? "The seasonal method does not run the lag-1 annual residual screen; correlation between adjacent months is disclosed as a limitation instead." : "The dependence screen was not run because there were too few eligible years for a significance test."}</Unavailable>
      )}
      <p className="note">Failing to detect autocorrelation does not prove the years are independent — with about ten years the diagnostic has little power.</p>
    </>
  );
}

function Change({ lab }: { lab: Lab }) {
  const cp = lab.change_point;
  return (
    <>
      <p className="section-lede">A gradual trend is a steady drift; an abrupt change is a sudden jump between two levels, which can come from a real event or from a change in data sources.</p>
      {!cp || cp.status === "not_tested" ? (
        <Unavailable>{cp?.reason ?? "No change-point check was run."}</Unavailable>
      ) : (
        <dl className="kv">
          <dt>Result</dt><dd>{cp.status === "step_detected" ? `Possible step between ${cp.last_year_before} and ${cp.first_year_after}` : "No sudden step detected"}</dd>
          <dt>Pettitt p-value</dt><dd className="mono">{fmt(cp.pettitt_p_value, 4)}</dd>
          <dt>Mean before / after</dt><dd className="mono">{fmt(cp.mean_before, 3)} / {fmt(cp.mean_after, 3)}</dd>
          <dt>Step fits better than a line</dt><dd>{cp.step_fits_better_than_line ? "yes" : "no"}</dd>
        </dl>
      )}
      <p className="note">Pettitt's test is also triggered by smooth trends, so a step is reported only when a two-level model fits better than a straight line. It looks for a single change point only.</p>
    </>
  );
}

function Assumptions() {
  const items: [string, string[]][] = [
    ["OLS", ["Assumes the mean changes linearly with time.", "Squared errors make it sensitive to outliers and to values at the ends of the record.", "Inference would need independent, normally distributed residuals with constant spread — so here OLS is descriptive only."]],
    ["Theil–Sen", ["The median of all pairwise slopes; robust to a minority of outliers.", "Still summarises a straight-line change; strong curvature or seasonality can make one slope misleading."]],
    ["Mann–Kendall", ["Tests for a monotonic (consistently rising or falling) trend, not a straight line.", "Tied values are handled with a variance correction.", "Autocorrelation inflates false positives; results are screened and labelled indicative.", "Significance is not proof of cause, and non-significance is not proof of no trend."]],
    ["Seasonal Kendall", ["Compares each calendar month only with the same month in other years.", "Months are used only with data in at least 70% of years.", "Treats months as independent; correlation between neighbouring months is not corrected, so p-values may be optimistic."]],
    ["Confidence intervals", ["A 95% interval is a range of slopes consistent with the data under the method's assumptions.", "It is shown only when the method supports it; otherwise the reason is given — intervals are never invented."]],
  ];
  return (
    <div className="assumption-grid">
      {items.map(([title, points]) => (
        <section key={title} className="assumption-card" aria-label={title}><h3>{title}</h3><ul>{points.map((p) => <li key={p}>{p}</li>)}</ul></section>
      ))}
    </div>
  );
}

export default function MethodsLab({ analysis }: { analysis: Analysis }) {
  const [tab, setTab] = useState<TabId>("overview");
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const lab = analysis.methods_lab;
  if (!lab) return <Unavailable>This analysis response does not include Statistical Methods Lab data. Re-run the investigation.</Unavailable>;

  function onKey(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    const keys: Record<string, number> = { ArrowRight: 1, ArrowLeft: -1 };
    let next: number;
    if (e.key in keys) next = (index + keys[e.key]! + LAB_TABS.length) % LAB_TABS.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = LAB_TABS.length - 1;
    else return;
    e.preventDefault();
    const id = LAB_TABS[next]!.id;
    setTab(id);
    refs.current[id]?.focus();
  }

  const label = LAB_TABS.find((t) => t.id === tab)!.label;
  return (
    <div className="methods-lab">
      <div className="lab-tabs" role="tablist" aria-label="Statistical methods">
        {LAB_TABS.map((t, i) => (
          <button key={t.id} id={`lab-tab-${t.id}`} ref={(el) => { refs.current[t.id] = el; }} role="tab" type="button"
            aria-selected={tab === t.id} aria-controls={`lab-panel-${t.id}`} tabIndex={tab === t.id ? 0 : -1}
            className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)} onKeyDown={(e) => onKey(e, i)}>
            {t.id === "estimators" && lab.seasonal ? "Seasonal estimators" : t.label}
          </button>
        ))}
      </div>
      <section id={`lab-panel-${tab}`} role="tabpanel" aria-labelledby={`lab-tab-${tab}`} className="lab-panel" tabIndex={0}>
        <h3 className="lab-panel-title">{tab === "estimators" && lab.seasonal ? "Seasonal estimators" : label}</h3>
        {tab === "overview" && <Overview lab={lab} a={analysis} />}
        {tab === "estimators" && <Estimators lab={lab} a={analysis} />}
        {tab === "significance" && <Significance lab={lab} />}
        {tab === "dependence" && <Dependence lab={lab} />}
        {tab === "change" && <Change lab={lab} />}
        {tab === "simulation" && <OutlierExperiment />}
        {tab === "assumptions" && <Assumptions />}
      </section>
    </div>
  );
}
