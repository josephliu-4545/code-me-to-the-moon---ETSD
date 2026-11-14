import type { Analysis } from "../../api/types";
import { trendVerdict } from "../../lib/verdict";

/** Data lineage from source product to finding, built only from the analysis metadata. */
export default function EvidenceChain({ analysis }: { analysis: Analysis }) {
  const a = analysis;
  const v = trendVerdict(a);
  const steps = [
    { k: "Source", v: `${a.dataset.source}`, d: `${a.dataset.title ?? a.dataset.id} · ${a.dataset.version}`, note: a.dataset.provenance.replace(/_/g, " ") },
    { k: "Footprint", v: a.spatial_support.resolution, d: a.spatial_support.description },
    { k: "Annual value", v: a.units.annual_value, d: a.variable.annual_value_definition },
    { k: "Eligibility", v: `${a.coverage.eligible_years} of ${a.coverage.years_requested} years`, d: "Years passing the completeness rules" },
    { k: "Method", v: a.trend?.result_level_label ?? "No trend computed", d: a.trend?.mann_kendall ? "Theil–Sen slope + Mann–Kendall test" : "Theil–Sen slope only, or annual summaries" },
    { k: "Finding", v: v.label, d: v.note, finding: true },
  ];
  return (
    <ol className="chain" aria-label="Evidence chain from source data to finding">
      {steps.map((s, i) => (
        <li key={s.k} className={`chain-step ${s.finding ? `chain-finding verdict-${v.kind}` : ""}`}>
          <span className="chain-node mono" aria-hidden>{String(i + 1).padStart(2, "0")}</span>
          <span className="chain-k">{s.k}</span>
          <span className="chain-v">{s.v}</span>
          <span className="chain-d">{s.d}</span>
          {s.note && <span className="chain-note">{s.note}</span>}
        </li>
      ))}
    </ol>
  );
}
