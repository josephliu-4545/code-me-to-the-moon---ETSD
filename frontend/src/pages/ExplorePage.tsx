import { useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { Analysis, AnalysisRequest, VariableInfo } from "../api/types";
import { isUnreachable } from "../api/types";
import AnalysisControls from "../components/AnalysisControls";
import LocationPanel from "../components/LocationPanel";
import type { Footprint } from "../components/MapView";
import { ErrorBox, Loading } from "../components/ResultPanels";
import MissionFindings from "../components/expedition/MissionFindings";
import MapBoundary from "../components/explore/MapBoundary";
import LaunchCraft from "../components/explore/LaunchCraft";
import Starfield from "../components/layout/Starfield";
import DiscoveryChamber from "../components/explore/DiscoveryChamber";
import { boxPatch, boxProblem, circleProblem, regionLimits } from "../lib/region";
import type { EditableRegion } from "../lib/regionInteraction";
import { signed } from "../lib/format";
import { periodLabel, trendVerdict } from "../lib/verdict";
import { useLaunchSequence } from "../state/launch";
import { requestIdentity, selectionBox, toRequest, type Selection } from "../state/selection";
import type { Theme } from "../state/theme";
import { analysisKey, findSnapshot, useAnalysis } from "../state/useAnalysis";

const MapView = lazy(() => import("../components/MapView"));

interface Props {
  variables: VariableInfo[];
  selection: Selection;
  onChange: (patch: Partial<Selection>) => void;
  submitted: AnalysisRequest | null;
  onSubmit: () => void;
  theme?: Theme;
  submittedPlace: string;
  snapshot: Analysis | null;
  onSnapshot: (value: Analysis | null) => void;
  /** Shared loader (App): loads the saved snapshot for the submitted request; resolves false if none exists. */
  onLoadSnapshot?: () => Promise<boolean>;
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
    return { kind: "cell", bounds: { west, south, east, north }, approximate: false, label: `${(east-west).toFixed(3)}° × ${(north-south).toFixed(3)}° box (area-weighted mean)` };
  }
  if (selection.variable === "ndvi") {
    const r = selection.mode === "region" ? selection.radiusKm : 0.25;
    return { kind: "circle", center: [selection.latitude, selection.longitude], radiusKm: r, label: `${r} km sampling circle` };
  }
  return null;
}

/** True when the controls no longer match the investigation the findings describe. */
export function selectionDiffers(selection: Selection, submitted: AnalysisRequest | null): boolean {
  return !!submitted && requestIdentity(toRequest(selection)) !== requestIdentity(submitted);
}

function scrollToEl(el: HTMLElement | null) {
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  el?.scrollIntoView?.({ behavior: reduce ? "auto" : "smooth", block: "start" });
}

export default function ExplorePage({ variables, selection, onChange, submitted, onSubmit, submittedPlace, snapshot, onSnapshot, onLoadSnapshot, theme = "dark" }: Props) {
  const queryClient = useQueryClient();
  const [cancelled, setCancelled] = useState(false);
  const query = useAnalysis(submitted);
  const [snapshotMissing, setSnapshotMissing] = useState(false);
  const analysis = cancelled ? undefined : query.data ?? (query.isError ? snapshot ?? undefined : undefined);
  const sameAsSubmitted =
    submitted && requestIdentity(submitted) === requestIdentity(toRequest(selection));
  const footprint = useMemo(() => footprintFor(selection, sameAsSubmitted ? analysis : undefined), [selection, analysis, sameAsSubmitted]);
  const info = variables.find(v => v.id === selection.variable);
  const region = useMemo<EditableRegion | null>(() => {
    if (selection.mode !== "region" || !info?.modes.region) return null;
    if (info.region_shape === "bbox") {
      const limits = regionLimits(info), bounds = selectionBox(selection);
      return limits && !boxProblem(bounds, limits) ? { kind: "box", bounds, limits } : null;
    }
    if (selection.variable === "ndvi" && info.max_radius_km && !circleProblem(selection.latitude, selection.radiusKm, info.max_radius_km))
      return { kind: "circle", center: [selection.longitude, selection.latitude], radiusKm: selection.radiusKm, maxRadius: info.max_radius_km };
    return null;
  }, [selection, info]);
  const unreachable = isUnreachable(query.error);
  const resultsRef = useRef<HTMLElement>(null);
  const launchRef = useRef<HTMLButtonElement>(null);
  const beaconRef = useRef<HTMLSpanElement>(null);
  const sequence = useLaunchSequence(query.isFetching, query.isError, requestIdentity(submitted), query.isSuccess || query.isError);
  const { phase, launch, cancel } = sequence;
  const stale = selectionDiffers(selection, submitted);

  useEffect(() => {
    // On stacked (narrow) layouts, bring new results into view.
    if ((query.isError || (query.data && phase === "completed")) && window.innerWidth <= 960) scrollToEl(resultsRef.current);
  }, [query.data, query.isError, phase]);

  async function loadSnapshot() {
    if (!submitted) return;
    if (onLoadSnapshot) {
      setSnapshotMissing(!(await onLoadSnapshot()));
      return;
    }
    const s = await findSnapshot(submitted);
    onSnapshot(s);
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
    phase === "ignition" ? "Investigation launched. Retrieving NASA data…" :
    query.isFetching ? "Analysis running. Retrieving NASA data and computing statistics…" :
    phase === "cancelled" ? "Investigation cancelled." :
    phase === "failed" ? "The investigation did not complete." :
    verdict ? `Findings ready: ${verdict.label}.` : "";

  return (
    <div className="explore">
      <LaunchCraft phase={phase} run={sequence.run} reduced={sequence.reduced} origin={launchRef} destination={beaconRef} />
      <h1 className="sr-only">Explore Earth</h1>
      <p className="sr-only" role="status" aria-live="polite">{statusText}</p>
      <section className="stage" aria-label="Earth from orbit and investigation controls">
        <div className="space-decor" aria-hidden="true">
          <span className="space-satellite space-satellite-a"><i /><b /></span>
          <span className="space-satellite space-satellite-b"><i /><b /></span>
          <span className="space-comet" />
          <span className="space-particle space-particle-a" />
          <span className="space-particle space-particle-b" />
          <span className="space-particle space-particle-c" />
        </div>
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
                footprint={selection.mode === "region" && !region ? null : footprint ? { ...footprint, confirmed: !!sameAsSubmitted && !!analysis } : null}
                theme={theme}
                region={region}
                onRegionChange={(r) => onChange(r.kind === "box" ? boxPatch(r.bounds) : { longitude: r.center[0], latitude: r.center[1], radiusKm: r.radiusKm, placeName: "" })}
                onSelect={(lat, lon) => onChange({ latitude: lat, longitude: lon, placeName: "" })}
              />
            </Suspense>
          </MapBoundary>
        </div>
        <div className="stage-caption" aria-hidden>
          <p className="kicker">Orbital observatory / 01</p>
          <p className="stage-title">A living planet.<br />A longer perspective.</p>
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
            launchRef={launchRef}
            onAnalyze={() => {
              setCancelled(false);
              onSnapshot(null);
              setSnapshotMissing(false);
              const nextKey = requestIdentity(toRequest(selection));
              launch(nextKey);
              // Repeating the same investigation must still execute a request.
              if (nextKey === requestIdentity(submitted)) void query.refetch();
              onSubmit();
            }}
            busy={query.isFetching}
            status={submitted && (
              <div className="dossier-status">
                {query.isFetching ? (
                  <p className="ds-line"><span className="orbit-loader orbit-sm" aria-hidden><span /></span>{phase === "ignition" ? "Launching investigation…" : "Analysis running — retrieving NASA data"}</p>
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

      <section id="findings" className={`findings ${(phase === "docking" || phase === "completed") ? "has-arrived" : ""}`} ref={resultsRef} aria-label="Mission findings" tabIndex={-1}>
        <DiscoveryChamber phase={phase} active={!!analysis || query.isFetching} />
        <div className="findings-inner">
          <div className={`results-beacon beacon-${phase}`}><span ref={beaconRef} aria-hidden className="beacon-ring" /><span>Mission Findings</span><small>Launch visualization represents your analysis request, not a spacecraft mission.</small></div>
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
          {query.isFetching && <button className="btn btn-ghost" type="button" onClick={() => { cancel(); setCancelled(true); void queryClient.cancelQueries({ queryKey: analysisKey(submitted), exact: true }); }}>Cancel investigation</button>}
          {cancelled && <p role="status">Investigation cancelled. Provider work already started may finish in the background.</p>}
          {query.isFetching && <Loading label="Retrieving NASA data and computing statistics…" />}
          {query.isError && !snapshot && (
            <ErrorBox
              error={query.error}
              onRetry={() => { setCancelled(false); launch(requestIdentity(submitted)); void query.refetch(); }}
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
              <MissionFindings analysis={analysis} place={submittedPlace} />
            </article>
          )}
        </div>
      </section>
    </div>
  );
}
