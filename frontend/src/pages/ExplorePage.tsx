import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { Analysis, AnalysisRequest, VariableInfo } from "../api/types";
import { isUnreachable } from "../api/types";
import AnalysisControls from "../components/AnalysisControls";
import LocationPanel from "../components/LocationPanel";
import type { Footprint } from "../components/MapView";
import { Cautions, ErrorBox, Limitations, Loading, MethodNotes, ProvenanceCard, ResultSummary } from "../components/ResultPanels";
import SeriesChart from "../components/SeriesChart";
import TrendChart from "../components/TrendChart";
import MapBoundary from "../components/explore/MapBoundary";
import Starfield from "../components/layout/Starfield";
import SeasonalChart from "../components/science/SeasonalChart";
import { signed } from "../lib/format";
import { periodLabel, trendVerdict } from "../lib/verdict";
import { useLaunchSequence } from "../state/launch";
import { selectionBox, toRequest, type Selection } from "../state/selection";
import type { Theme } from "../state/theme";
import { findSnapshot, useAnalysis } from "../state/useAnalysis";

const MapView = lazy(() => import("../components/MapView"));

interface Props {
  variables: VariableInfo[];
  selection: Selection;
  onChange: (patch: Partial<Selection>) => void;
  submitted: AnalysisRequest | null;
  onSubmit: () => void;
  theme?: Theme;
}

export function footprintFor(selection: Selection, analysis: Analysis | undefined): Footprint | null {
  if (analysis) {
    const s = analysis.spatial_support;
    if (s.bbox) return { kind: "cell", bounds: s.bbox, approximate: false, label: `${s.resolution}` };
    if (s.cell) return { kind: "cell", bounds: s.cell.bounds, approximate: s.cell.approximate, label: `${s.resolution}${s.cell.approximate ? " (approximate)" : ""}` };
    if (s.radius_km) return { kind: "circle", center: [s.requested.latitude, s.requested.longitude], radiusKm: s.radius_km, label: `${s.radius_km} km sampling circle` };
  }
  if (selection.variable === "precipitation" && selection.mode === "region") {
    const [west, south, east, north] = selectionBox(selection);
    return { kind: "cell", bounds: { west, south, east, north }, approximate: false, label: `${selection.boxSpan.toFixed(1)}° box (area-weighted mean)` };
  }
  if (selection.variable === "ndvi") {
    const r = selection.mode === "region" ? selection.radiusKm : 0.25;
    return { kind: "circle", center: [selection.latitude, selection.longitude], radiusKm: r, label: `${r} km sampling circle` };
  }
  return null;
}

/** True when the controls no longer match the investigation the findings describe. */
export function selectionDiffers(selection: Selection, submitted: AnalysisRequest | null): boolean {
  return !!submitted && JSON.stringify(toRequest(selection)) !== JSON.stringify(submitted);
}

function scrollToEl(el: HTMLElement | null) {
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  el?.scrollIntoView?.({ behavior: reduce ? "auto" : "smooth", block: "start" });
}

export default function ExplorePage({ variables, selection, onChange, submitted, onSubmit, theme = "dark" }: Props) {
  const query = useAnalysis(submitted);
  const [snapshot, setSnapshot] = useState<Analysis | null>(null);
  const [snapshotMissing, setSnapshotMissing] = useState(false);
  const [submittedPlace, setSubmittedPlace] = useState(selection.placeName);
  const analysis = query.data ?? (query.isError ? snapshot ?? undefined : undefined);
  const sameAsSubmitted =
    submitted && Math.abs(submitted.latitude - selection.latitude) < 1e-4 && Math.abs(submitted.longitude - selection.longitude) < 1e-4;
  const footprint = useMemo(() => footprintFor(selection, sameAsSubmitted ? analysis : undefined), [selection, analysis, sameAsSubmitted]);
  const unreachable = isUnreachable(query.error);
  const resultsRef = useRef<HTMLElement>(null);
  const { phase, launch } = useLaunchSequence(query.isFetching, query.isError);
  const stale = selectionDiffers(selection, submitted);

  useEffect(() => {
    // On stacked (narrow) layouts, bring new results into view.
    if ((query.data || query.isError) && window.innerWidth <= 960) scrollToEl(resultsRef.current);
  }, [query.data, query.isError]);

  async function loadSnapshot() {
    if (!submitted) return;
    const s = await findSnapshot(submitted);
    setSnapshot(s);
    setSnapshotMissing(!s);
  }

  function jumpToFindings(e: React.MouseEvent) {
    // Scroll within the page instead of changing the hash (the hash selects the section).
    e.preventDefault();
    scrollToEl(resultsRef.current);
    resultsRef.current?.focus({ preventScroll: true });
  }

  const verdict = analysis && !query.isFetching ? trendVerdict(analysis) : null;
  const statusText =
    phase === "launching" ? "Investigation launched. Retrieving NASA data…" :
    query.isFetching ? "Analysis running. Retrieving NASA data and computing statistics…" :
    phase === "aborted" ? "The investigation did not complete." :
    verdict ? `Findings ready: ${verdict.label}.` : "";

  return (
    <div className="explore">
      <h1 className="sr-only">Explore Earth</h1>
      <p className="sr-only" role="status" aria-live="polite">{statusText}</p>
      <section className="stage" aria-label="Earth from orbit and investigation controls">
        <div className="stage-map">
          <Starfield className="stage-stars" />
          <svg className="stage-orbits" viewBox="0 0 1000 600" preserveAspectRatio="xMidYMid slice" aria-hidden>
            <ellipse cx="650" cy="330" rx="470" ry="150" transform="rotate(-14 650 330)" />
            <ellipse cx="650" cy="330" rx="560" ry="200" transform="rotate(-14 650 330)" className="orbit-far" />
          </svg>
          <MapBoundary>
            <Suspense fallback={<div className="map-wrap map-loading"><span className="orbit-loader" aria-hidden><span /></span><span>Bringing Earth into view…</span></div>}>
              <MapView
                latitude={selection.latitude}
                longitude={selection.longitude}
                footprint={footprint}
                theme={theme}
                onSelect={(lat, lon) => onChange({ latitude: lat, longitude: lon, placeName: "" })}
              />
            </Suspense>
          </MapBoundary>
        </div>
        <div className="stage-caption" aria-hidden>
          <p className="kicker">Mission 01 · Explore Earth</p>
          <p className="stage-title">Discover the signals<br />of a changing planet.</p>
        </div>
        <aside className="dossier" aria-label="Investigation">
          <header className="dossier-head">
            <p className="kicker">Investigation brief</p>
            <p className="dossier-title">What has changed here?</p>
          </header>
          <LocationPanel
            latitude={selection.latitude}
            longitude={selection.longitude}
            placeName={selection.placeName}
            onChange={(lat, lon, name) => onChange({ latitude: lat, longitude: lon, placeName: name })}
          />
          <AnalysisControls
            variables={variables}
            selection={selection}
            onChange={onChange}
            phase={phase}
            onAnalyze={() => {
              setSnapshot(null);
              setSnapshotMissing(false);
              setSubmittedPlace(selection.placeName);
              launch();
              onSubmit();
            }}
            busy={query.isFetching}
            status={submitted && (
              <div className="dossier-status">
                {query.isFetching ? (
                  <p className="ds-line"><span className="orbit-loader orbit-sm" aria-hidden><span /></span>{phase === "launching" ? "Launching investigation…" : "Analysis running — retrieving NASA data"}</p>
                ) : verdict && analysis ? (
                  <a className={`ds-result ${stale ? "is-stale" : ""}`} href="#findings" onClick={jumpToFindings}>
                    <span className={`ds-verdict verdict-${verdict.kind}`}>{verdict.label}</span>
                    {analysis.trend?.slope != null && <span className="mono ds-slope">{signed(analysis.trend.slope, 4)} {analysis.trend.slope_units}</span>}
                    <span className="ds-link">{stale ? "Earlier run · view ↓" : "View findings ↓"}</span>
                  </a>
                ) : query.isError ? (
                  <a className="ds-result ds-error" href="#findings" onClick={jumpToFindings}>Investigation did not complete · details below ↓</a>
                ) : null}
              </div>
            )}
          />
        </aside>
      </section>

      <section id="findings" className={`findings ${phase === "arrived" ? "has-arrived" : ""}`} ref={resultsRef} aria-label="Mission findings" tabIndex={-1}>
        <div className="findings-inner">
          {!submitted && (
            <div className="findings-intro">
              <p className="kicker">Mission findings</p>
              <h2 className="intro-title">Choose a place and an Earth signal, then launch the investigation.</h2>
              <p className="intro-body">Any point on Earth can be analysed, subject to each NASA dataset’s coverage. Findings show what changed, how much, how strong the evidence is, and what the data cannot tell you.</p>
              <ol className="intro-steps">
                <li><span className="mono">01</span> Place<small>Search, click the globe, or type coordinates</small></li>
                <li><span className="mono">02</span> Signal<small>Six NASA-derived variables</small></li>
                <li><span className="mono">03</span> Window<small>Within each dataset’s record</small></li>
                <li><span className="mono">04</span> Evidence<small>Trend, uncertainty, provenance</small></li>
              </ol>
            </div>
          )}
          {query.isFetching && <Loading label="Retrieving NASA data and computing statistics…" />}
          {query.isError && !snapshot && (
            <ErrorBox
              error={query.error}
              onRetry={() => { launch(); query.refetch(); }}
              extra={unreachable ? (
                <>
                  <button type="button" className="btn btn-ghost" onClick={loadSnapshot}>Show saved snapshot</button>
                  {snapshotMissing && <span className="status-hint">No saved snapshot exists for this exact request.</span>}
                </>
              ) : null}
            />
          )}
          {analysis && !query.isFetching && (
            <article className="results arrive" key={`${analysis.variable.id}-${analysis.period.start}-${analysis.spatial_support.requested.latitude}-${analysis.data_status}`}>
              {stale && (
                <p className="stale-notice" role="note">
                  <strong>Controls changed since this investigation.</strong> These findings still describe {analysis.variable.name} at {submittedPlace || "the earlier point"}, {periodLabel(analysis)}. Launch again to investigate the new selection.
                </p>
              )}
              <ResultSummary analysis={analysis} place={submittedPlace} />
              <section className="layer layer-data" aria-labelledby="layer-4">
                <h3 id="layer-4" className="layer-title"><span className="layer-num" aria-hidden>04</span>What does the data look like?</h3>
                <div className="charts">
                  <TrendChart analysis={analysis} />
                  <SeriesChart analysis={analysis} />
                  <SeasonalChart analysis={analysis} />
                </div>
              </section>
              <Cautions analysis={analysis} />
              <div className="dossier-foot">
                <ProvenanceCard analysis={analysis} />
                <div className="stack">
                  <MethodNotes analysis={analysis} />
                  <Limitations analysis={analysis} />
                  <a className="text-link" href="#evaluation">Open Mission Control for the full evidence review →</a>
                </div>
              </div>
            </article>
          )}
        </div>
      </section>
    </div>
  );
}
