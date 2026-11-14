import type { CompareResponse, CoverageStatus, DatasetEvaluation } from "../../api/compareTypes";
import { reasonLabel } from "../../lib/format";

const STATUS: Record<CoverageStatus, { label: string; symbol: string }> = {
  valid: { label: "Valid observation", symbol: "✓" },
  missing: { label: "Missing observation", symbol: "○" },
  excluded: { label: "Excluded by quality control", symbol: "×" },
  provisional: { label: "Provisional or incomplete", symbol: "!" },
  outside_coverage: { label: "Outside dataset coverage", symbol: "—" },
  unavailable: { label: "Information unavailable", symbol: "?" },
};

function Matrix({ data, rows, resolution }: { data: CompareResponse; rows: [string, DatasetEvaluation][]; resolution: "annual" | "monthly" }) {
  const periods = [...new Set(rows.flatMap(([, evaluation]) => evaluation.cells.map((cell) => cell.period)))].sort();
  return (
    <section className="eval-matrix-section" aria-labelledby={`coverage-${resolution}`}>
      <h3 id={`coverage-${resolution}`} className="eval-subtitle">{resolution === "monthly" ? "Monthly coverage" : "Annual coverage"}</h3>
      <p className="note">{rows[0]?.[1].resolution_note}</p>
      <div className="eval-matrix-wrap" tabIndex={0} aria-label={`${resolution} dataset coverage matrix`}>
        <table className="eval-matrix">
          <thead><tr><th scope="col">Dataset</th>{periods.map((period) => <th scope="col" key={period}>{period}</th>)}</tr></thead>
          <tbody>
            {rows.map(([key, evaluation]) => {
              const byPeriod = new Map(evaluation.cells.map((cell) => [cell.period, cell]));
              const datasetName = data.results[key]?.entry.name ?? key;
              return (
                <tr key={key}>
                  <th scope="row">{datasetName}</th>
                  {periods.map((period) => {
                    const cell = byPeriod.get(period);
                    const status = cell?.status ?? "unavailable";
                    const detail = cell?.reasons.map(reasonLabel).join("; ");
                    const label = `${datasetName}, ${period}: ${STATUS[status].label}${detail ? ` — ${detail}` : ""}`;
                    return <td key={period}><button type="button" className={`eval-cell eval-${status}`} aria-label={label} title={label}>{STATUS[status].symbol}<span className="sr-only">{STATUS[status].label}</span></button></td>;
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function CoverageMatrix({ data }: { data: CompareResponse }) {
  const evaluations = data.evaluation?.datasets ?? {};
  const rows = data.datasets_requested.flatMap((key) => evaluations[key] ? [[key, evaluations[key]] as [string, DatasetEvaluation]] : []);
  return (
    <>
      <div className="eval-legend" aria-label="Coverage status legend">
        {(Object.entries(STATUS) as [CoverageStatus, { label: string; symbol: string }][]).map(([status, item]) => (
          <span key={status}><span className={`eval-cell eval-${status}`} aria-hidden>{item.symbol}</span>{item.label}</span>
        ))}
      </div>
      {(["annual", "monthly"] as const).map((resolution) => {
        const matching = rows.filter(([, evaluation]) => evaluation.resolution === resolution);
        return matching.length ? <Matrix key={resolution} data={data} rows={matching} resolution={resolution} /> : null;
      })}
      <div className="eval-quality-grid">
        {rows.map(([key, evaluation]) => {
          const denominator = evaluation.completeness.expected_within_supported_coverage;
          return (
            <article className="eval-quality-card" key={key}>
              <h3>{data.results[key]?.entry.name ?? key}</h3>
              <strong className="mono">{evaluation.completeness.valid} / {denominator} valid {evaluation.resolution === "monthly" ? "months" : "years"}</strong>
              <p>{evaluation.completeness.percentage === null ? "Not calculable" : `${evaluation.completeness.percentage.toFixed(1)}% complete`}</p>
              <p className="note">{evaluation.completeness.label}</p>
              <p className="note">Requested: {evaluation.requested_period.start} → {evaluation.requested_period.end_exclusive} · Product record: {evaluation.supported_period.start} → {evaluation.supported_period.end ?? "present"}</p>
              <p className="note">Missing {evaluation.counts.missing} · QC excluded {evaluation.counts.excluded} · Provisional {evaluation.counts.provisional} · Outside record {evaluation.counts.outside_coverage}</p>
            </article>
          );
        })}
      </div>
    </>
  );
}
