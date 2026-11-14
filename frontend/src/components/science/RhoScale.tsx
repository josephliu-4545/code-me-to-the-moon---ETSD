import { fmt } from "../../lib/format";

/** Spearman ρ on a fixed −1…+1 scale. Null values are shown as withheld, never as zero. */
export default function RhoScale({ value, label }: { value: number | null; label: string }) {
  const pos = value === null ? null : `${((value + 1) / 2) * 100}%`;
  return (
    <div className="rho">
      <div className="rho-head">
        <span className="rho-label">{label}</span>
        <span className={`rho-value mono ${value === null ? "is-withheld" : ""}`}>{value === null ? "withheld" : `ρ = ${fmt(value, 3)}`}</span>
      </div>
      <div className="rho-track" role="img" aria-label={value === null ? `${label}: withheld` : `${label}: Spearman rho ${fmt(value, 3)} on a scale from −1 to +1`}>
        <span className="rho-zero" />
        {pos && <span className="rho-dot" style={{ left: pos }} />}
      </div>
      <div className="rho-ticks" aria-hidden><span>−1</span><span>0</span><span>+1</span></div>
    </div>
  );
}
