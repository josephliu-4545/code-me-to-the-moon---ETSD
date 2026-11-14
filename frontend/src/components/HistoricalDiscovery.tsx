import { useEffect, useMemo, useState } from "react";
import type { Analysis, AnalysisRequest } from "../api/types";
import { fmt, signed } from "../lib/format";
import { annualHistory, monthlyHistory, observationDifference } from "../lib/history";
import PeriodComparisonPanel from "./PeriodComparisonPanel";
import TrendChart from "./TrendChart";
import SeriesChart from "./SeriesChart";
import Disclosure from "./ui/Disclosure";

export default function HistoricalDiscovery({ analysis, request }: { analysis: Analysis; request?: AnalysisRequest }) {
  const [mode, setMode] = useState<"annual" | "monthly">("annual");
  const [selected, setSelected] = useState("");
  const [compare, setCompare] = useState("");
  const [playing, setPlaying] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(() => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!query) return;
    const update = () => { setReducedMotion(query.matches); if (query.matches) setPlaying(false); };
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  const annual = useMemo(() => annualHistory(analysis), [analysis]);
  const monthly = useMemo(() => monthlyHistory(analysis), [analysis]);
  const rows = mode === "annual" ? annual : monthly;
  const current = rows.find((p) => p.date === selected) ?? rows[0];
  const reference = rows.find((p) => p.date === compare) ?? rows[rows.length - 1];
  const units = mode === "annual" ? (analysis.discovery?.history.annual_units ?? analysis.units.annual_value) :
    analysis.discovery?.history.monthly_units ?? analysis.series_definition?.match(/\(([^)]+)\)\s*$/)?.[1] ?? analysis.units.annual_value;
  const difference = observationDifference(current, reference);
  const differenceUnits = analysis.variable.id === "relative_humidity" || analysis.variable.id === "extreme_heat" ? "percentage points" : units;
  const index = Math.max(0, rows.findIndex((p) => p.date === current?.date));
  const select = (date: string) => { setPlaying(false); setSelected(date); };
  const nextIndex = (from: number, step: 1 | -1) => {
    for (let i = from + step; i >= 0 && i < rows.length; i += step) if (rows[i]!.value !== null) return i;
    return -1;
  };
  const step = (direction: 1 | -1) => { const i = nextIndex(index, direction); if (i >= 0) { setPlaying(false); setSelected(rows[i]!.date); } };
  useEffect(() => {
    if (!playing || reducedMotion) return;
    const timer = window.setInterval(() => {
      setSelected((prev) => {
        const at = Math.max(0, rows.findIndex((p) => p.date === (prev || rows[0]?.date)));
        const i = nextIndex(at, 1);
        if (i < 0) { setPlaying(false); return prev; }
        return rows[i]!.date;
      });
    }, 1200);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, reducedMotion, rows]);
  return (
    <section id="historical-discovery" className="history-workspace" tabIndex={-1} aria-labelledby="history-title">
      <header className="history-header"><div><p className="kicker">03 / Historical Discovery</p>
        <h2 id="history-title">Time travel through evidence.</h2>
        <p className="note">Inspect the recorded values behind the finding. Empty dates stay empty.</p></div>
        <div className="history-modes" role="group" aria-label="Observation resolution">
          <button type="button" className="btn btn-ghost" aria-pressed={mode === "annual"} onClick={() => { setMode("annual"); setPlaying(false); setSelected(""); setCompare(""); }}>Annual summaries</button>
          <button type="button" className="btn btn-ghost" aria-pressed={mode === "monthly"} disabled={!monthly.length || !analysis.series_definition} onClick={() => { setMode("monthly"); setPlaying(false); setSelected(""); setCompare(""); }}>Monthly observations</button>
        </div>
      </header>
      {!monthly.length && <p className="note">No monthly observations were supplied for this investigation.</p>}
      {mode === "annual" ? <TrendChart analysis={analysis} onSelect={select} selectedDate={current?.date} /> : <SeriesChart analysis={analysis} onSelect={select} selectedDate={current?.date} />}
      {current ? <>
        <div className="history-scrubber">
          <label htmlFor="history-time">Inspect {mode === "annual" ? "year" : "month"}: <strong className="mono">{current.date}</strong></label>
          <input id="history-time" type="range" min={0} max={Math.max(0, rows.length - 1)} value={index} aria-valuetext={`${current.date}: ${current.value === null ? "No usable value" : `${fmt(current.value, 3)} ${units}`}; ${current.status}`} onChange={(e) => select(rows[Number(e.target.value)]!.date)} />
          <div className="history-playback" role="group" aria-label="Timeline playback">
            <button type="button" className="btn btn-ghost" onClick={() => step(-1)} disabled={nextIndex(index, -1) < 0}>Previous observation</button>
            <button type="button" className="btn btn-ghost" aria-pressed={playing} onClick={() => setPlaying((v) => !v)} disabled={reducedMotion || nextIndex(index, 1) < 0}>{playing ? "Pause" : "Play"}</button>
            <button type="button" className="btn btn-ghost" onClick={() => step(1)} disabled={nextIndex(index, 1) < 0}>Next observation</button>
            <p className="note" role="status">{reducedMotion ? "Automatic playback is off because your system requests reduced motion; use the step buttons." : playing ? `Playing ${current.date}` : "Playback skips dates with no usable value."}</p>
          </div>
          <div className="history-endpoints mono"><span>{rows[0]?.date}</span><span>{rows[rows.length - 1]?.date}</span></div>
        </div>
        <div className="history-inspection">
          <section className="sheet" aria-label="Selected observation"><h3 className="sheet-title">Observation passport</h3>
            <dl className="kv"><dt>Date</dt><dd className="mono">{current.date}</dd>
              <dt>Value</dt><dd className="mono">{current.value === null ? "Unavailable" : `${fmt(current.value, 4)} ${units}`}</dd>
              <dt>Status</dt><dd>{current.status}</dd><dt>Product</dt><dd>{analysis.dataset.id} / {analysis.dataset.version}</dd>
              <dt>Aggregation</dt><dd>{mode === "annual" ? analysis.variable.annual_value_definition : analysis.series_definition}</dd>
              <dt>Spatial support</dt><dd>{analysis.spatial_support.description} ({analysis.spatial_support.resolution})</dd></dl>
          </section>
          <section className="sheet" aria-label="Compare observations"><h3 className="sheet-title">Compare two observations</h3>
            <label className="field">Compare selected {current.date} with
              <select value={reference?.date ?? ""} onChange={(e) => setCompare(e.target.value)}>{rows.map((p) => <option key={p.date} value={p.date}>{p.date}{p.value === null ? " — unavailable" : !p.eligible ? " — excluded" : ""}</option>)}</select>
            </label>
            <p className="history-difference mono">{difference === null ? "Comparison unavailable" : `${signed(difference, 4)} ${differenceUnits}`}</p>
            <p className="note">{reference?.date} minus {current.date}. {difference === null ? "Both dates need a usable value." : `Compared value: ${fmt(reference?.value, 4)} ${units}.`}</p>
            <p className="note">{reference?.status}</p>
            <p className="note">An observed difference, not the fitted slope or a significance test. Excluded annual values are descriptive only; months can differ seasonally.</p>
          </section>
        </div>
        <Disclosure summary="Select an observation from the evidence table" meta={`${rows.length} dates`}>
          <div className="table-wrap table-tall"><table className="table"><caption>{mode === "annual" ? "Annual summaries" : "Monthly observations"} — {units}; select a date to inspect it</caption>
            <thead><tr><th scope="col">Date</th><th scope="col">Value ({units})</th><th scope="col">Observation status</th></tr></thead>
            <tbody>{rows.map((p) => <tr key={p.date} className={p.date === current.date ? "history-selected" : ""}><th scope="row"><button type="button" className="history-date" aria-pressed={p.date === current.date} onClick={() => select(p.date)}>{p.date}</button></th><td className="mono">{fmt(p.value, 4)}</td><td>{p.status}</td></tr>)}</tbody>
          </table></div>
        </Disclosure>
      </> : <p className="note">No dated observations are available. A missing record is not evidence of no environmental change.</p>}
      {request && <PeriodComparisonPanel key={analysis.discovery?.analysis_id ?? JSON.stringify(request)} analysis={analysis} request={request} />}
    </section>
  );
}
