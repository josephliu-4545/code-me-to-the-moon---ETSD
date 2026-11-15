import type { Analysis, AnalysisRequest } from "../api/types";
import { ErrorBox, Loading } from "../components/ResultPanels";
import EmptyState from "../components/ui/EmptyState";
import PageHero from "../components/ui/PageHero";
import { fmt, fmtCoord, signed } from "../lib/format";
import { buildMissionReport, settingsUrl } from "../lib/report";
import { periodLabel, slopeName, testName, trendVerdict } from "../lib/verdict";
import { useAnalysis } from "../state/useAnalysis";

function downloadReport(report: ReturnType<typeof buildMissionReport>) {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `earth-trend-mission-${report.investigation.id ?? "report"}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function MissionReportPage({ submitted, place, snapshot }: { submitted: AnalysisRequest | null; place: string; snapshot: Analysis | null }) {
  const query = useAnalysis(submitted);
  const analysis = query.data ?? (query.isError ? snapshot ?? undefined : undefined);
  const report = analysis && submitted ? buildMissionReport(analysis, submitted, place) : null;
  const verdict = analysis ? trendVerdict(analysis) : null;
  return (
    <div className="page page-report">
      <PageHero kicker="Mission Report · reproducible evidence" title={<>Carry the discovery <em>beyond the observatory</em></>} tone="notebook">
        <p>A print-ready scientific record and machine-readable export of the exact submitted investigation.</p>
      </PageHero>
      <div className="page-body report-body">
        {!submitted && <EmptyState title="No investigation to report." action={<a className="btn btn-ink" href="#explore">Launch an investigation →</a>}><p>The report is generated only from a completed analysis response.</p></EmptyState>}
        {submitted && query.isFetching && !analysis && <Loading label="Retrieving the investigation for the report…" />}
        {submitted && query.isError && !analysis && <ErrorBox error={query.error} onRetry={() => query.refetch()} />}
        {analysis && submitted && report && verdict && (
          <article className="mission-report" aria-labelledby="report-title">
            <header className="report-cover">
              <div><p className="kicker">Earth System Trend Detective</p><h2 id="report-title">{analysis.variable.name} · {place || fmtCoord(submitted.latitude, submitted.longitude)}</h2><p>{periodLabel(analysis)} · {analysis.spatial_support.mode} investigation</p></div>
              <div className="report-actions no-print">
                <button type="button" className="btn btn-ink" onClick={() => window.print()}>Print report</button>
                <button type="button" className="btn btn-ghost" onClick={() => downloadReport(report)}>Download evidence JSON</button>
                <a className="btn btn-ghost" href={settingsUrl(submitted, place)}>Restore settings</a>
              </div>
            </header>
            <section className="report-finding">
              <p className="kicker">Primary finding</p><h3>{verdict.label}</h3><p>{verdict.note}</p>
              <dl className="report-metrics">
                <div><dt>{slopeName(analysis)}</dt><dd>{analysis.trend?.slope == null ? "Unavailable" : `${signed(analysis.trend.slope, 4)} ${analysis.trend.slope_units ?? analysis.units.slope}`}</dd></div>
                <div><dt>{testName(analysis)}</dt><dd>{analysis.trend?.mann_kendall ? `${analysis.trend.mann_kendall.is_statistically_significant ? "Significant (indicative)" : "Not significant"}; p = ${fmt(analysis.trend.mann_kendall.p_value, 4)}` : "Not reported"}</dd></div>
                <div><dt>Eligible years</dt><dd>{analysis.coverage.eligible_years} of {analysis.coverage.years_requested}</dd></div>
              </dl>
            </section>
            <div className="report-columns">
              <section><h3>Investigation identity</h3><dl className="report-list"><div><dt>ID</dt><dd className="mono">{analysis.investigation?.id ?? "not supplied"}</dd></div><div><dt>Requested point</dt><dd>{fmtCoord(submitted.latitude, submitted.longitude)}</dd></div><div><dt>Spatial support</dt><dd>{analysis.spatial_support.description} · {analysis.spatial_support.resolution}</dd></div><div><dt>Dataset</dt><dd>{analysis.dataset.source} · {analysis.dataset.id} · {analysis.dataset.version}</dd></div><div><dt>Data status</dt><dd>{analysis.data_status.replaceAll("_", " ")}</dd></div></dl></section>
              <section><h3>Scientific guardrails</h3><ul>{[...analysis.caveats, ...analysis.limitations].map((item) => <li key={item}>{item}</li>)}</ul></section>
            </div>
            <details className="report-evidence"><summary>Annual evidence ({analysis.annual.length} years)</summary><div className="table-wrap"><table className="table"><thead><tr><th>Year</th><th>Value ({analysis.units.annual_value})</th><th>Eligibility</th></tr></thead><tbody>{analysis.annual.map((point) => <tr key={point.year}><th>{point.year}</th><td className="mono">{fmt(point.value, 3)}</td><td>{point.eligible ? "Eligible" : point.reasons.join("; ") || "Excluded"}</td></tr>)}</tbody></table></div></details>
            <footer className="report-footer"><p>Generated {new Date(report.generated_at).toLocaleString()} from the application response. The JSON export preserves annual and monthly evidence, methodology, caveats, provenance, and the submitted request.</p></footer>
          </article>
        )}
      </div>
    </div>
  );
}
