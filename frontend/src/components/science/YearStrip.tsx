import type { AnnualPoint } from "../../api/types";
import { fmt, reasonLabel } from "../../lib/format";

/** One mark per requested year: eligible (used in the trend), excluded (shown, not used), or no value. */
export default function YearStrip({ annual, units }: { annual: AnnualPoint[]; units: string }) {
  return (
    <ol className="year-strip" aria-label="Year-by-year eligibility">
      {annual.map((y) => {
        const state = y.eligible ? "eligible" : y.value === null ? "empty" : "excluded";
        const reasons = y.reasons.map(reasonLabel).join("; ");
        const text = `${y.year}: ${y.value === null ? "no annual value" : `${fmt(y.value, 3)} ${units}`}, ${y.eligible ? "eligible for the trend" : `excluded${reasons ? ` (${reasons})` : ""}`}`;
        return (
          <li key={y.year} className={`ys ys-${state}`} aria-label={text} title={text}>
            <span className="ys-mark" aria-hidden />
            <span className="ys-year" aria-hidden>{String(y.year).slice(2)}<span className="ys-century">{String(y.year).slice(0, 2)}</span></span>
          </li>
        );
      })}
    </ol>
  );
}
