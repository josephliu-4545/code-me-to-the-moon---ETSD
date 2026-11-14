import { useMemo, useState } from "react";
import type { CompareResponse, EvaluationMetric, PairComparison } from "../../api/compareTypes";
import CoverageMatrix from "./CoverageMatrix";
import DifferenceChart from "./DifferenceChart";

function metricValue(metric: EvaluationMetric): string {
  if (metric.value === null) return "Unavailable";
  if (typeof metric.value === "boolean") return metric.value ? "Yes" : "No";
  return `${metric.value.toFixed(3)}${metric.units ? ` ${metric.units}` : ""}`;
}

function MetricTable({ pair }: { pair: PairComparison }) {
  return (
    <div className="table-wrap">
      <table className="table eval-metrics">
        <thead><tr><th>Metric</th><th>Value</th><th>Matched observations</th><th>Meaning and limitations</th></tr></thead>
        <tbody>{(pair.metrics ?? []).map((metric) => (
          <tr key={metric.id}>
            <th scope="row">{metric.name}</th>
            <td className="mono">{metricValue(metric)}</td>
            <td>{metric.matched_observations}</td>
            <td><p>{metric.definition}</p><p>{metric.interpretation}</p><p className="note">{metric.value === null ? metric.unavailable_reason : metric.limitations}</p></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export default function EvaluationLab({ data }: { data: CompareResponse }) {
  const pairs = data.evaluation?.pairs ?? [];
  const [pairIndex, setPairIndex] = useState(0);
  const pair = pairs[Math.min(pairIndex, Math.max(0, pairs.length - 1))];
  const names = useMemo<[string, string] | null>(() => pair ? [
    data.results[pair.datasets[0]]?.entry.name ?? pair.datasets[0],
    data.results[pair.datasets[1]]?.entry.name ?? pair.datasets[1],
  ] : null, [data, pair]);

  if (!data.evaluation) return <p className="cmp-banner cmp-warn">Evaluation evidence is unavailable from this backend response.</p>;
  return (
    <div className="evaluation-lab reveal">
      <section className="lab-section" aria-labelledby="coverage-heading">
        <div className="lab-section-head"><p className="kicker">Evidence 01</p><h2 id="coverage-heading" className="section-title">Coverage and quality control</h2><p className="section-lede">Coverage percentages use only periods inside each product's supported record. Missing, excluded, provisional, and pre-record periods remain distinct.</p></div>
        <CoverageMatrix data={data} />
      </section>

      <section className="lab-section" aria-labelledby="agreement-heading">
        <div className="lab-section-head"><p className="kicker">Evidence 02</p><h2 id="agreement-heading" className="section-title">Matched observations and agreement</h2></div>
        {!pair || !names ? <p className="note">Pair metrics are unavailable because fewer than two datasets returned comparable results.</p> : <>
          {pairs.length > 1 && <label className="field eval-pair-select"><span className="field-label">Dataset pair</span><select value={pairIndex} onChange={(event) => setPairIndex(Number(event.target.value))}>{pairs.map((candidate, index) => <option key={candidate.datasets.join()} value={index}>{data.results[candidate.datasets[0]]?.entry.name} vs {data.results[candidate.datasets[1]]?.entry.name}</option>)}</select></label>}
          <p><strong>{pair.matched_observations?.count ?? pair.common_eligible_years.length} matched annual observations</strong>{pair.matched_observations?.period ? ` · ${pair.matched_observations.period.start}–${pair.matched_observations.period.end}` : ""}</p>
          <p className="note">{names[0]} valid: {pair.matched_observations?.valid_observations[pair.datasets[0]]?.join(", ") || "none"}. {names[1]} valid: {pair.matched_observations?.valid_observations[pair.datasets[1]]?.join(", ") || "none"}. Only periods valid in both products support the metrics below.</p>
          <MetricTable pair={pair} />
          <DifferenceChart pair={pair} names={names} />
        </>}
      </section>

      <section className="lab-section" aria-labelledby="limitations-heading">
        <div className="lab-section-head"><p className="kicker">Evidence 03</p><h2 id="limitations-heading" className="section-title">Scientific interpretation</h2></div>
        <ul className="bullets">{data.evaluation.cautions.map((caution) => <li key={caution}>{caution}</li>)}</ul>
        <p className="note">Native spatial footprints and production systems are disclosed in the Comparison provenance table. Agreement cannot identify a more accurate product without a suitable independent validation reference.</p>
      </section>
    </div>
  );
}
