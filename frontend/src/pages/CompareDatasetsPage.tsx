import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { compareApi, type CompareRequest } from "../api/compareClient";
import type { CompareResponse, DatasetInfo, VariableDatasets } from "../api/compareTypes";
import { AgreementBanner, DatasetStatusCards, PairTable, ProvenanceTable, SummaryTable } from "../components/compare/ComparisonPanels";
import OverlayChart from "../components/compare/OverlayChart";
import { ErrorBox, Limitations, Loading, ProvenanceCard, ResultSummary } from "../components/ResultPanels";
import SeriesChart from "../components/SeriesChart";
import TrendChart from "../components/TrendChart";
import PageHero from "../components/ui/PageHero";
import { fmtCoord } from "../lib/format";
import type { Selection } from "../state/selection";
import "../compare.css";

const VARIABLE_NAMES: Record<string, string> = {
  temperature: "Air temperature (2 m)",
  precipitation: "Precipitation",
  soil_moisture: "Soil moisture",
  relative_humidity: "Relative humidity",
  extreme_heat: "Extreme heat frequency",
  ndvi: "Vegetation (NDVI)",
};

export function validateCompare(selected: string[], datasets: DatasetInfo[], startYear: number, endYearInclusive: number): string | null {
  if (selected.length < 2) return "Select at least two datasets.";
  if (selected.length > 4) return "Select at most four datasets.";
  if (startYear > endYearInclusive) return "The start year must not be after the end year.";
  const span = endYearInclusive - startYear + 1;
  const chosen = datasets.filter((d) => selected.includes(d.key));
  const tooLong = chosen.find((d) => span > d.max_years);
  if (tooLong) return `${tooLong.name} allows at most ${tooLong.max_years} years per request; shorten the period.`;
  return null;
}

export function coverageWarnings(selected: DatasetInfo[], startYear: number, endYearInclusive: number, latitude: number): string[] {
  const out: string[] = [];
  for (const d of selected) {
    const [lo, hi] = d.latitude_limits;
    if (latitude < lo || latitude > hi) out.push(`${d.name} does not cover latitude ${latitude.toFixed(2)}° (${lo}° to ${hi}°).`);
    if (Number(d.available_from.slice(0, 4)) > startYear) out.push(`${d.name} starts in ${d.available_from.slice(0, 4)}; earlier years will have no data.`);
    if (d.available_to && Number(d.available_to.slice(0, 4)) < endYearInclusive) out.push(`${d.name} ends on ${d.available_to}; later years will have no data.`);
  }
  return out;
}

export default function CompareDatasetsPage({ selection }: { selection: Selection }) {
  const catalog = useQuery({ queryKey: ["datasets-catalog"], queryFn: ({ signal }) => compareApi.datasets(signal), staleTime: Infinity });
  const [variable, setVariable] = useState("temperature");
  const [chosen, setChosen] = useState<Record<string, string[]>>({});
  const [submitted, setSubmitted] = useState<CompareRequest | null>(null);
  const [view, setView] = useState<string>("comparison");

  const info: VariableDatasets | undefined = catalog.data?.variables.find((v) => v.variable === variable);
  const datasets = info?.datasets ?? [];
  const selected = chosen[variable] ?? datasets.map((d) => d.key).slice(0, 3);
  const selectedInfo = datasets.filter((d) => selected.includes(d.key));
  const problem = info?.comparison_available ? validateCompare(selected, datasets, selection.startYear, selection.endYearInclusive) : null;
  const warnings = coverageWarnings(selectedInfo, selection.startYear, selection.endYearInclusive, selection.latitude);

  const query = useQuery({
    queryKey: ["compare", submitted],
    queryFn: ({ signal }) => compareApi.compare(submitted!, signal),
    enabled: submitted !== null,
  });
  const data: CompareResponse | undefined = query.data;
  const order = useMemo(() => (data ? data.datasets_requested : []), [data]);
  const succeeded = data ? order.filter((k) => data.results[k]?.analysis) : [];
  const resultsOk = data ? succeeded.map((k) => data.results[k]!) : [];

  function toggle(key: string) {
    const current = selected;
    setChosen({ ...chosen, [variable]: current.includes(key) ? current.filter((k) => k !== key) : [...current, key] });
  }

  function run() {
    setView("comparison");
    setSubmitted({
      variable,
      datasets: datasets.filter((d) => selected.includes(d.key)).map((d) => d.key),
      latitude: Number(selection.latitude.toFixed(4)),
      longitude: Number(selection.longitude.toFixed(4)),
      startYear: selection.startYear,
      endYear: selection.endYearInclusive + 1,
    });
  }

  if (catalog.isPending) return <div className="page page-control page-status"><Loading label="Loading the dataset catalog…" /></div>;
  if (catalog.isError) return <div className="page page-control page-status"><ErrorBox error={catalog.error} onRetry={() => catalog.refetch()} /></div>;

  return (
    <div className="page page-control compare-page">
      <PageHero kicker="Mission Control · Compare Datasets" title={<>Do independent records <em>tell the same story</em>?</>} tone="control">
        <p>
          Analyse one variable with several NASA and partner datasets, each independently with its own quality rules, then compare them descriptively.
          Location and period come from Explore Earth: <strong>{selection.placeName || "custom point"}</strong>, <span className="mono">{fmtCoord(selection.latitude, selection.longitude)}</span>, {selection.startYear}–{selection.endYearInclusive} (point analysis at each dataset's native grid cell).
        </p>
      </PageHero>
      <div className="page-body">

      <section className="lab-section" aria-labelledby="cmp-var-h">
        <div className="lab-section-head"><p className="kicker">Step 1</p><h2 id="cmp-var-h" className="section-title">1 · Variable</h2></div>
        <div className="cmp-variables" role="radiogroup" aria-label="Variable to compare">
          {catalog.data!.variables.map((v) => (
            <button key={v.variable} type="button" role="radio" aria-checked={v.variable === variable}
              className={`variable-chip ${v.variable === variable ? "active" : ""}`} disabled={!v.comparison_available}
              title={v.not_yet_available_reason ?? undefined}
              onClick={() => { setVariable(v.variable); setSubmitted(null); }}>
              <span className="chip-name">{VARIABLE_NAMES[v.variable] ?? v.variable}</span>
              <span className="chip-source">{v.comparison_available ? `${v.datasets.length} datasets` : "single dataset"}</span>
            </button>
          ))}
        </div>
        {catalog.data!.variables.filter((v) => !v.comparison_available).map((v) => (
          <p key={v.variable} className="note">{VARIABLE_NAMES[v.variable]}: {v.not_yet_available_reason}</p>
        ))}
      </section>

      {info?.comparison_available && (
        <section className="lab-section" aria-labelledby="cmp-ds-h">
          <div className="lab-section-head"><p className="kicker">Step 2</p><h2 id="cmp-ds-h" className="section-title">2 · Datasets (choose 2–4)</h2></div>
          <div className="cmp-dataset-grid">
            {datasets.map((d) => (
              <label key={d.key} className={`cmp-dataset ${selected.includes(d.key) ? "on" : ""}`}>
                <input type="checkbox" checked={selected.includes(d.key)} onChange={() => toggle(d.key)} />
                <span>
                  <strong>{d.name}</strong>{d.is_primary && <span className="cmp-tag">primary</span>}
                  <span className="cmp-meta muted block">{d.provider}</span>
                  <span className="cmp-meta block">{d.product_type} · {d.spatial_resolution} · {d.temporal_resolution}</span>
                  <span className="cmp-meta muted block">{d.available_from.slice(0, 4)}–{d.available_to ? d.available_to.slice(0, 4) : "present"} · {d.coverage_note}</span>
                </span>
              </label>
            ))}
          </div>
          {info.relationships.length > 0 && (
            <details className="note">
              <summary>How these datasets relate</summary>
              <ul>
                {info.relationships.filter((r) => r.datasets.every((k) => selected.includes(k))).map((r) => (
                  <li key={r.datasets.join()}>
                    {datasets.find((d) => d.key === r.datasets[0])?.name} vs {datasets.find((d) => d.key === r.datasets[1])?.name}: {r.note}
                    {!r.numerically_comparable && " They measure different quantities, so values are shown side by side, not differenced."}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {warnings.map((w) => <p key={w} className="warn-text">{w}</p>)}
          {problem && <p className="error-text" role="alert">{problem}</p>}
          <button type="button" className="btn btn-primary cmp-run" onClick={run} disabled={!!problem || query.isFetching}>
            {query.isFetching ? "Analysing each dataset…" : "Compare datasets"}
          </button>
        </section>
      )}

      {query.isFetching && <Loading label="Retrieving and analysing each dataset independently…" />}
      {query.isError && <ErrorBox error={query.error} onRetry={() => query.refetch()} />}

      {data && !query.isFetching && (
        <>
          <AgreementBanner data={data} />
          <DatasetStatusCards data={data} order={order} />
          <div className="cmp-tabs" role="tablist" aria-label="Result view">
            <button role="tab" aria-selected={view === "comparison"} className={view === "comparison" ? "active" : ""} onClick={() => setView("comparison")}>Comparison</button>
            {succeeded.map((k) => (
              <button key={k} role="tab" aria-selected={view === k} className={view === k ? "active" : ""} onClick={() => setView(k)}>
                {data.results[k]!.entry.name}
              </button>
            ))}
          </div>

          {view === "comparison" ? (
            <>
              {resultsOk.length > 0 && (data.comparison?.all_numerically_comparable || resultsOk.length === 1 ? (
                <OverlayChart results={resultsOk} units={resultsOk[0]!.entry.units} />
              ) : (
                <div className="cmp-small-multiples">
                  <p className="note">These datasets measure different quantities or units, so each is shown on its own axis instead of one shared chart.</p>
                  {resultsOk.map((r) => <TrendChart key={r.entry.key} analysis={r.analysis!} />)}
                </div>
              ))}
              <section className="lab-section" aria-labelledby="cmp-sum-h">
                <div className="lab-section-head"><h2 id="cmp-sum-h" className="section-title">Trend summary</h2></div>
                <SummaryTable data={data} order={order} />
              </section>
              {data.comparison && (
                <section className="lab-section" aria-labelledby="cmp-pair-h">
                  <div className="lab-section-head"><h2 id="cmp-pair-h" className="section-title">Pairwise comparison</h2></div>
                  <p className="note">Common eligible years for all successful datasets: {data.comparison.common_eligible_years_all.join(", ") || "none"}.</p>
                  <PairTable data={data} />
                </section>
              )}
              <section className="lab-section" aria-labelledby="cmp-prov-h">
                <div className="lab-section-head"><h2 id="cmp-prov-h" className="section-title">Provenance and quality-control differences</h2></div>
                <ProvenanceTable data={data} order={order} />
              </section>
              <section className="lab-section" aria-labelledby="cmp-cav-h">
                <div className="lab-section-head"><h2 id="cmp-cav-h" className="section-title">Caveats</h2></div>
                <ul className="bullets">{data.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
              </section>
            </>
          ) : (
            data.results[view]?.analysis && (
              <div className="results">
                <ResultSummary analysis={data.results[view]!.analysis!} />
                <TrendChart analysis={data.results[view]!.analysis!} />
                <SeriesChart analysis={data.results[view]!.analysis!} />
                <div className="cmp-two-col">
                  <ProvenanceCard analysis={data.results[view]!.analysis!} />
                  <Limitations analysis={data.results[view]!.analysis!} />
                </div>
              </div>
            )
          )}
        </>
      )}
      </div>
    </div>
  );
}
