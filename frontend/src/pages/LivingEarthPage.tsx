import { useMemo, useState } from "react";
import type { Analysis, AnalysisRequest, AnnualPoint } from "../api/types";
import { ErrorBox, Loading } from "../components/ResultPanels";
import EmptyState from "../components/ui/EmptyState";
import PageHero from "../components/ui/PageHero";
import { fmt, reasonLabel } from "../lib/format";
import { useAnalysis } from "../state/useAnalysis";

function finite(points: AnnualPoint[]) {
  return points.filter((point): point is AnnualPoint & { value: number } => typeof point.value === "number" && Number.isFinite(point.value));
}

export function visualIndex(analysis: Analysis, year: number): number | null {
  const values = finite(analysis.annual);
  const selected = values.find((point) => point.year === year)?.value;
  if (selected === undefined) return null;
  const lo = Math.min(...values.map((point) => point.value));
  const hi = Math.max(...values.map((point) => point.value));
  return hi === lo ? 0.5 : (selected - lo) / (hi - lo);
}

export default function LivingEarthPage({ submitted, snapshot }: { submitted: AnalysisRequest | null; snapshot: Analysis | null }) {
  const query = useAnalysis(submitted);
  const analysis = query.data ?? (query.isError ? snapshot ?? undefined : undefined);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const year = analysis?.annual.some((item) => item.year === selectedYear)
    ? selectedYear
    : analysis?.annual.at(-1)?.year ?? null;
  const point = analysis?.annual.find((item) => item.year === year);
  const index = analysis && year !== null ? visualIndex(analysis, year) : null;
  const monthly = useMemo(() => analysis?.series.filter((item) => item.date.startsWith(`${year}-`)) ?? [], [analysis, year]);

  return (
    <div className="page page-living">
      <PageHero kicker="Living Earth · data-linked visual story" title={<>See one record as a <em>changing signal</em></>} tone="cosmic">
        <p>Select a year to connect the retrieved value, its eligibility, and its monthly evidence to an artistic orbital scene.</p>
      </PageHero>
      <div className="page-body living-body">
        {!submitted && <EmptyState title="Launch an investigation first." action={<a className="btn btn-ink" href="#explore">Explore Earth →</a>}><p>Living Earth uses the active investigation’s real annual and monthly observations.</p></EmptyState>}
        {submitted && query.isFetching && !analysis && <Loading label="Retrieving the investigation’s observations…" />}
        {submitted && query.isError && !analysis && <ErrorBox error={query.error} onRetry={() => query.refetch()} />}
        {analysis && year !== null && (
          <section className="living-console" aria-labelledby="living-title">
            <div className={`living-scene ${index === null ? "is-missing" : ""}`} style={{ "--signal": index ?? 0.5 } as React.CSSProperties}>
              <div className="living-nebula" aria-hidden="true" />
              <div className="living-orbit" aria-hidden="true"><span className="living-satellite" /></div>
              <div className="living-earth" aria-hidden="true"><span /></div>
              <div className="living-astronaut" aria-hidden="true"><span className="helmet" /><span className="body" /><span className="pack" /></div>
              <p className="living-art-label">Artistic signal mapping · not a historical photograph or geographic reconstruction</p>
            </div>
            <div className="living-readout">
              <p className="kicker">Year in focus · {year}</p>
              <h2 id="living-title" className="section-title">{analysis.variable.name}</h2>
              <p className="living-value mono">{point?.value == null ? "No annual value" : `${fmt(point.value, 3)} ${analysis.units.annual_value}`}</p>
              <p className={`living-state ${point?.eligible ? "is-eligible" : ""}`}>{point?.eligible ? "Eligible for trend analysis" : "Shown for context; excluded from the trend"}</p>
              {!point?.eligible && point?.reasons.length ? <p className="note">{point.reasons.map(reasonLabel).join("; ")}</p> : null}
              <label className="living-year" htmlFor="living-year"><span>Travel through the record</span><strong className="mono">{year}</strong></label>
              <input id="living-year" type="range" min={0} max={Math.max(0, analysis.annual.length - 1)} value={Math.max(0, analysis.annual.findIndex((item) => item.year === year))} onChange={(event) => setSelectedYear(analysis.annual[Number(event.target.value)]?.year ?? year)} />
              <div className="living-scale" aria-hidden="true"><span>{analysis.annual[0]?.year}</span><span>{analysis.annual.at(-1)?.year}</span></div>
              <dl className="living-facts">
                <div><dt>Dataset</dt><dd>{analysis.dataset.source} · {analysis.dataset.id}</dd></div>
                <div><dt>Footprint</dt><dd>{analysis.spatial_support.description}</dd></div>
                <div><dt>Monthly evidence</dt><dd>{monthly.filter((item) => item.value !== null).length} returned value(s) in {year}</dd></div>
              </dl>
              <p className="caveat">Brightness and color show only where this year falls within the minimum-to-maximum range of this retrieved series. They do not encode land cover, weather, or conditions at unobserved locations.</p>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
