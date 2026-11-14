import type { CompareResponse, DatasetResult, Outcome, PairComparison } from "../../api/compareTypes";
import { fmt, reasonLabel, signed } from "../../lib/format";
import { DATASET_COLORS } from "./OverlayChart";

const OUTCOME_TONE: Record<Outcome, "good" | "info" | "warn" | "bad"> = {
  inference: "good",
  descriptive_only: "info",
  insufficient_coverage: "warn",
  no_data: "warn",
  unsupported_location: "warn",
  unsupported_mode: "warn",
  outside_record: "warn",
  provider_error: "bad",
};

const LINEAGE_LABEL: Record<PairComparison["lineage"], string> = {
  same_lineage: "Same lineage (not independent)",
  partially_related: "Partially related (shared inputs)",
  independent: "Independent sources",
};

const AGREEMENT_LABEL: Record<string, string> = {
  consistent: "Consistent",
  mixed: "Mixed",
  conflicting_trend_direction: "Conflicting trend direction",
  partially_assessable: "Partially assessable",
  not_assessable: "Not assessable",
};

export function outcomeTone(o: Outcome) {
  return OUTCOME_TONE[o] ?? "info";
}

export function DatasetStatusCards({ data, order }: { data: CompareResponse; order: string[] }) {
  return (
    <div className="cmp-status-grid">
      {order.map((key, i) => {
        const r = data.results[key]!;
        const a = r.analysis;
        return (
          <article key={key} className={`cmp-status cmp-${outcomeTone(r.outcome)}`} aria-label={`${r.entry.name}: ${r.message}`}>
            <header>
              <span className="cmp-swatch" style={{ background: DATASET_COLORS[i % 4] }} aria-hidden />
              <strong>{r.entry.name}</strong>
            </header>
            <p className="cmp-outcome">{r.message}</p>
            {a && (
              <p className="note">
                {a.coverage.eligible_years}/{a.coverage.years_requested} eligible years
                {a.trend?.slope != null ? ` · ${signed(a.trend.slope, 4)} ${a.trend.slope_units}` : ""}
              </p>
            )}
            {!a && r.outcome === "provider_error" && <p className="note">The other datasets are still shown. Retry later.</p>}
            <p className="note">{r.entry.provider} · {r.entry.spatial_resolution}</p>
          </article>
        );
      })}
    </div>
  );
}

export function AgreementBanner({ data }: { data: CompareResponse }) {
  if (!data.comparison) {
    return (
      <div className="cmp-banner cmp-warn" role="status">
        <strong>No comparison:</strong> {data.comparison_unavailable_reason}. Results for the datasets that succeeded are shown individually.
      </div>
    );
  }
  const ag = data.comparison.agreement;
  const tone = ag.level === "consistent" ? "good" : ag.level === "conflicting_trend_direction" ? "bad" : ag.level === "mixed" ? "warn" : "info";
  return (
    <div className={`cmp-banner cmp-${tone}`} role="status">
      <strong>Agreement: {AGREEMENT_LABEL[ag.level] ?? ag.level}.</strong> {ag.explanation}
      <div className="note">{ag.caution}</div>
    </div>
  );
}

export function SummaryTable({ data, order }: { data: CompareResponse; order: string[] }) {
  const pairsWithCommon = data.comparison?.pairs.filter((p) => p.common_period_slopes) ?? [];
  const commonSlope = (key: string) => pairsWithCommon.find((p) => p.common_period_slopes?.[key] !== undefined)?.common_period_slopes?.[key];
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr><th>Dataset</th><th>Outcome</th><th>Eligible years</th><th>Trend (full request)</th><th>95% interval</th><th>Trend (common years)</th><th>Units</th></tr>
        </thead>
        <tbody>
          {order.map((key) => {
            const r: DatasetResult = data.results[key]!;
            const t = r.analysis?.trend;
            const cs = commonSlope(key);
            return (
              <tr key={key}>
                <td>{r.entry.name}{r.entry.is_primary && <span className="cmp-tag">primary</span>}</td>
                <td><span className={`cmp-pill cmp-${outcomeTone(r.outcome)}`}>{r.outcome.replace(/_/g, " ")}</span></td>
                <td>{r.analysis ? `${r.analysis.coverage.eligible_years}/${r.analysis.coverage.years_requested}` : "—"}</td>
                <td>{t?.slope != null ? `${signed(t.slope, 4)} ${t.slope_units}` : t?.slope_unavailable_reason ?? "—"}</td>
                <td>{t?.confidence_interval ? `${signed(t.confidence_interval[0], 3)} to ${signed(t.confidence_interval[1], 3)}` : "—"}</td>
                <td>{cs !== undefined ? signed(cs, 4) : "—"}</td>
                <td>{r.entry.units}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="note">
        “Common years” slopes use only calendar years eligible in both datasets of a pair (descriptive; no significance test), so they compare like with like.
      </p>
    </div>
  );
}

export function PairTable({ data }: { data: CompareResponse }) {
  if (!data.comparison) return null;
  const name = (k: string) => data.results[k]?.entry.name ?? k;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr><th>Pair</th><th>Lineage</th><th>Common years</th><th>Mean difference</th><th>Spearman ρ</th><th>ρ of year-to-year changes</th><th>Trend signs agree</th></tr>
        </thead>
        <tbody>
          {data.comparison.pairs.map((p) => (
            <tr key={p.datasets.join()}>
              <td>{name(p.datasets[0])} vs {name(p.datasets[1])}</td>
              <td title={p.lineage_note}>{LINEAGE_LABEL[p.lineage]}</td>
              <td>{p.common_eligible_years.length}</td>
              <td>{p.numerically_comparable ? (p.mean_difference === null ? "—" : `${signed(p.mean_difference, 3)} ${p.difference_units ?? ""}`) : "not compared"}</td>
              <td>{p.spearman_rho === null ? "withheld" : fmt(p.spearman_rho, 2)}</td>
              <td>{p.spearman_rho_year_to_year === null ? "withheld" : fmt(p.spearman_rho_year_to_year, 2)}</td>
              <td>{p.slope_sign_agreement === null ? "—" : p.slope_sign_agreement ? "yes" : "no"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="note cmp-notes">
        {data.comparison.pairs.map((p) => (
          <li key={p.datasets.join()}>
            <strong>{name(p.datasets[0])} vs {name(p.datasets[1])}:</strong> {p.lineage_note}
            {p.not_comparable_reason ? ` ${p.not_comparable_reason}` : ""}
            {p.unavailable_reasons.length ? ` Withheld: ${p.unavailable_reasons.map(reasonLabel).join("; ")}.` : ""}
          </li>
        ))}
      </ul>
      <p className="note">Mean difference = first minus second, over common eligible years; a systematic difference, not an error. No dataset is treated as ground truth, and no p-values are given for correlations.</p>
    </div>
  );
}

export function ProvenanceTable({ data, order }: { data: CompareResponse; order: string[] }) {
  const rows: [string, (k: string) => string][] = [
    ["Collection", (k) => data.results[k]!.entry.collection_id],
    ["Version", (k) => data.results[k]!.entry.version],
    ["Type", (k) => data.results[k]!.entry.product_type],
    ["Measures", (k) => data.results[k]!.entry.measurement],
    ["Spatial support", (k) => data.results[k]!.entry.spatial_resolution],
    ["Temporal sampling", (k) => data.results[k]!.entry.temporal_resolution],
    ["Record", (k) => `${data.results[k]!.entry.available_from} → ${data.results[k]!.entry.available_to ?? "present"}`],
    ["Coverage", (k) => data.results[k]!.entry.coverage_note],
    ["Quality control", (k) => data.results[k]!.entry.quality_control],
    ["Lineage", (k) => data.results[k]!.entry.lineage],
    ["Licence", (k) => data.results[k]!.entry.license],
  ];
  return (
    <div className="table-wrap">
      <table className="table cmp-prov">
        <thead><tr><th></th>{order.map((k) => <th key={k}>{data.results[k]!.entry.name}</th>)}</tr></thead>
        <tbody>
          {rows.map(([label, get]) => (
            <tr key={label}><th scope="row">{label}</th>{order.map((k) => <td key={k}>{get(k)}</td>)}</tr>
          ))}
          <tr>
            <th scope="row">Citation</th>
            {order.map((k) => {
              const e = data.results[k]!.entry;
              return <td key={k}>{e.citation}{e.doi && <> · <a href={`https://doi.org/${e.doi}`} target="_blank" rel="noreferrer">doi:{e.doi}</a></>}</td>;
            })}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
