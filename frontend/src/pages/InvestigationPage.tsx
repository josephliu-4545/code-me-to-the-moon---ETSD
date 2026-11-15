import { useState, type MouseEvent } from "react";
import type { Analysis, AnalysisRequest } from "../api/types";
import ConsoleCards from "../components/explore/ConsoleCards";
import HistoricalDiscovery from "../components/HistoricalDiscovery";
import SpaceBackdrop from "../components/layout/SpaceBackdrop";
import { Cautions, ErrorBox, Limitations, Loading, MethodNotes, ProvenanceCard, ResultSummary } from "../components/ResultPanels";
import TrendChart from "../components/TrendChart";
import EmptyState from "../components/ui/EmptyState";
import PageHero from "../components/ui/PageHero";
import { fmt, perDecade } from "../lib/format";
import { trendVerdict } from "../lib/verdict";
import { toRequest, type Selection } from "../state/selection";
import { findSnapshot, useAnalysis } from "../state/useAnalysis";
import { selectionDiffers } from "./ExplorePage";

const EXAMPLE: AnalysisRequest = { variable: "temperature", latitude: 16.8661, longitude: 96.1951, startYear: 2015, endYear: 2025, mode: "point" };

interface Props {
  section: "history" | "findings";
  submitted: AnalysisRequest | null;
  selection: Selection;
  onChange: (patch: Partial<Selection>) => void;
  snapshot: Analysis | null;
  onStart: (request: AnalysisRequest) => void;
  onSnapshot: (snapshot: Analysis | null, request: AnalysisRequest) => void;
}

export default function InvestigationPage({ section, submitted, selection, onChange, snapshot, onStart, onSnapshot }: Props) {
  const query = useAnalysis(snapshot ? null : submitted);
  const analysis = snapshot ?? query.data;
  const [loadingExample, setLoadingExample] = useState(false);
  const [exampleError, setExampleError] = useState(false);
  const [actionLaunching, setActionLaunching] = useState(false);
  const isHistory = section === "history";
  const currentRequest = toRequest(selection);
  const stale = selectionDiffers(selection, submitted);

  async function loadExample() {
    setLoadingExample(true);
    setExampleError(false);
    const saved = await findSnapshot(EXAMPLE);
    if (saved) {
      onChange({ latitude: EXAMPLE.latitude, longitude: EXAMPLE.longitude, placeName: "Yangon, Myanmar", variable: "temperature", startYear: 2015, endYearInclusive: 2024, mode: "point" });
      onStart(EXAMPLE);
      onSnapshot(saved, EXAMPLE);
    } else setExampleError(true);
    setLoadingExample(false);
  }

  function animateAction(event: MouseEvent<HTMLDivElement>) {
    const target = (event.target as HTMLElement).closest<HTMLAnchorElement | HTMLButtonElement>(".investigation-page-links a, .empty-state .btn, .period-comparison .btn, .error-box .btn");
    if (!target || target.getAttribute("aria-disabled") === "true" || (target instanceof HTMLButtonElement && target.disabled)) return;
    const href = target instanceof HTMLAnchorElement ? target.getAttribute("href") : null;
    if (href?.startsWith("#")) event.preventDefault();
    setActionLaunching(false);
    requestAnimationFrame(() => setActionLaunching(true));
    window.setTimeout(() => {
      setActionLaunching(false);
      if (href?.startsWith("#")) window.location.hash = href.slice(1);
    }, 900);
  }

  const slope = analysis?.trend?.slope;
  const verdict = analysis ? trendVerdict(analysis) : null;
  const rail = analysis ? [
    { label: "Years used", value: String(analysis.trend?.eligible_years.length ?? analysis.annual.filter((point) => point.eligible).length).padStart(2, "0") },
    { label: "Per decade", value: slope == null ? "–" : fmt(perDecade(slope), 2) },
    { label: "Test", value: verdict?.kind === "increasing" || verdict?.kind === "decreasing" ? "Supported" : verdict?.kind === "unavailable" ? "None" : "Open" },
  ] : [];

  return (
    <div className={`page investigation-space space-page-${section}`}>
      <SpaceBackdrop tone={isHistory ? "history" : "findings"} />
      {rail.length > 0 && <dl className="stat-rail" aria-label="Investigation at a glance">{rail.map((item) => <div key={item.label} className="stat-rail-item"><dd className="mono">{item.value}</dd><dt>{item.label}</dt></div>)}</dl>}
      <PageHero
        kicker={isHistory ? "Historical Discovery" : "Mission Findings"}
        title={isHistory
          ? <><span className="title-line">Time travel</span><span className="title-line">through</span><em className="title-line">evidence.</em></>
          : <><span className="title-line">Explain</span><span className="title-line">the</span><em className="title-line">discovery.</em></>}
      >
        <p>{isHistory ? "Inspect annual and monthly records, trace data gaps, and compare observations and periods." : "What changed, by how much, and how strong is the evidence? Follow every conclusion back to the recorded data."}</p>
      </PageHero>
      <div className={`page-body investigation-flight-deck ${actionLaunching ? "is-launching" : ""}`} onClickCapture={animateAction}>
        <div className="row-gap investigation-page-links">
          <a className="btn btn-ghost" href="#explore">Choose location and signal</a>
          <a className="text-link" href={isHistory ? "#findings" : "#history"}>{isHistory ? "View Mission Findings" : "View Historical Discovery"}<span aria-hidden> →</span></a>
        </div>
        {!submitted && !analysis && <EmptyState title="Choose an investigation to explore" action={<div className="row-gap"><button className="btn btn-ghost" type="button" onClick={() => onStart(currentRequest)}>Analyze current selection</button><button className="btn btn-ghost" type="button" disabled={loadingExample} onClick={loadExample}>{loadingExample ? "Opening example…" : "View saved Yangon example"}</button></div>}>
          <p>Choose your location, signal and dates on Explore Earth, then launch. Or open the saved Yangon temperature record for 2015–2024. The example is a labelled snapshot of an earlier NASA retrieval.</p>
        </EmptyState>}
        {query.isFetching && <Loading label="Retrieving the investigation evidence." />}
        {query.isError && !analysis && <><ErrorBox error={query.error} onRetry={() => query.refetch()} /><button className="btn btn-ghost" type="button" disabled={loadingExample} onClick={loadExample}>View saved Yangon example</button></>}
        {exampleError && <p role="alert" className="note">The saved example could not be loaded. Run an investigation or retry.</p>}
        {stale && analysis && <p className="stale-notice" role="note"><strong>Selection changed.</strong> These results still describe {analysis.variable.name} at {analysis.spatial_support.requested.latitude.toFixed(4)}°, {analysis.spatial_support.requested.longitude.toFixed(4)}°. Return to Explore Earth and launch to update them.</p>}
        {analysis && <ConsoleCards analysis={analysis} />}
        {analysis && <div className="results" key={analysis.discovery?.analysis_id ?? JSON.stringify(submitted)}>
          {isHistory ? <HistoricalDiscovery analysis={analysis} request={submitted ?? undefined} /> : <>
            <ResultSummary analysis={analysis} historyPage />
            <TrendChart analysis={analysis} />
            <Cautions analysis={analysis} />
            <div className="dossier-foot"><ProvenanceCard analysis={analysis} /><div><MethodNotes analysis={analysis} /><Limitations analysis={analysis} /></div></div>
          </>}
        </div>}
      </div>
    </div>
  );
}
