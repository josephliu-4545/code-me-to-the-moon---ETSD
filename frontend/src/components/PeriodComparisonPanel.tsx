import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Analysis, AnalysisRequest, ComparisonWindow } from "../api/types";
import { api } from "../api/client";
import { fmt, reasonLabel, signed } from "../lib/format";
import { ErrorBox } from "./ResultPanels";

export default function PeriodComparisonPanel({ analysis, request }: { analysis: Analysis; request: AnalysisRequest }) {
  const firstYear = request.startYear;
  const lastYear = request.endYear - 1;
  const split = Math.floor((firstYear + lastYear) / 2);
  const [windows, setWindows] = useState<ComparisonWindow>({ first_start_year: firstYear, first_end_year: split, second_start_year: split + 1, second_end_year: lastYear });
  const [run, setRun] = useState<ComparisonWindow | null>(null);
  const query = useQuery({
    queryKey: ["period-comparison", analysis.discovery?.analysis_id, request, run],
    queryFn: ({ signal }) => api.periodComparison(request, analysis.discovery!.analysis_id, run!, signal),
    enabled: !!run && !!analysis.discovery && analysis.data_status !== "saved_snapshot",
    retry: false,
  });
  const problem = windows.first_start_year > windows.first_end_year || windows.second_start_year > windows.second_end_year ? "Start years must be at or before end years." :
    Math.max(windows.first_start_year, windows.second_start_year) <= Math.min(windows.first_end_year, windows.second_end_year) ? "Choose two non-overlapping periods." : null;
  const available = !!analysis.discovery && analysis.data_status !== "saved_snapshot";
  const years = Array.from({ length: Math.max(0, lastYear - firstYear + 1) }, (_, i) => firstYear + i);
  const fields: { key: keyof ComparisonWindow; label: string }[] = [
    { key: "first_start_year", label: "First period from" }, { key: "first_end_year", label: "First period through" },
    { key: "second_start_year", label: "Second period from" }, { key: "second_end_year", label: "Second period through" },
  ];
  return <section className="period-comparison sheet" aria-labelledby="period-comparison-title">
    <p className="kicker">Compare the record</p><h3 id="period-comparison-title" className="sheet-title">Two periods. One scientific basis.</h3>
    <p className="note">Compare the mean of eligible annual summaries from the same dataset and footprint. The backend calculates both means and their difference.</p>
    {!available && <p className="note">Period comparison needs a live or cached backend analysis with an evidence identity. Saved snapshots and older API results remain available for observation inspection.</p>}
    <div className="period-fields">{fields.map(({ key, label }) => <label className="field" key={key}>{label}<select value={windows[key]} disabled={!available} onChange={(e) => { setRun(null); setWindows({ ...windows, [key]: Number(e.target.value) }); }}>{years.map((y) => <option value={y} key={y}>{y}</option>)}</select></label>)}</div>
    {problem && available && <p className="note" role="alert">{problem}</p>}
    <button type="button" className="btn btn-ghost" disabled={!available || !!problem || query.isFetching} onClick={() => { if (run) void query.refetch(); else setRun({ ...windows }); }}>{query.isFetching ? "Comparing periods…" : "Compare periods"}</button>
    {query.isFetching && <p role="status" className="note">Calculating comparable period statistics from the submitted investigation.</p>}
    {query.isError && <ErrorBox error={query.error} onRetry={() => query.refetch()} />}
    {query.data && !query.isFetching && <div className="period-result" role="status">
      {query.data.analysis_id !== analysis.discovery?.analysis_id ? <p>The evidence identity changed. Run the investigation again.</p> : <>
        <div className="history-inspection">{[query.data.first, query.data.second].map((p, i) => <div key={i}><h4>{i === 0 ? "First" : "Second"} period: {p.start_year}–{p.end_year_inclusive}</h4>
          <p className="history-difference mono">{p.mean === null ? "Unavailable" : `${fmt(p.mean, 4)} ${query.data!.annual_units}`}</p>
          <p className="note">{p.count}/{p.expected_years} eligible years. {p.eligible_years.join(", ") || "No eligible years"}.</p>
          {p.excluded_years.length > 0 && <details><summary>Excluded years ({p.excluded_years.length})</summary><ul>{p.excluded_years.map((y) => <li key={y.year}>{y.year}: {y.reasons.map(reasonLabel).join("; ")}</li>)}</ul></details>}
        </div>)}</div>
        <p className="figure-label">Second minus first</p><p className="history-difference mono">{query.data.difference === null ? "Comparison unavailable: no eligible values in one or both periods" : `${signed(query.data.difference, 4)} ${query.data.units}`}</p>
        <p className="note">{query.data.statistic} Annual basis: {query.data.annual_value_definition}.</p>
        <ul className="limitations">{query.data.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        <p className="note mono">Evidence {query.data.analysis_id.slice(0, 16)} · retrieved {query.data.cache.retrieved_at}</p>
      </>}
    </div>}
  </section>;
}
