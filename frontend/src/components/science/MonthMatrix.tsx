import type { AnnualPoint } from "../../api/types";

const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** Valid versus missing months per year, built from represented_months / missing_months. */
export default function MonthMatrix({ annual }: { annual: AnnualPoint[] }) {
  if (!annual.some((y) => y.represented_months !== null)) return null;
  return (
    <div className="matrix-wrap">
      <table className="matrix">
        <caption className="sr-only">Months with valid data by year. Missing months are never filled.</caption>
        <thead>
          <tr>
            <th scope="col"><span className="sr-only">Year</span></th>
            {MONTHS.map((m, i) => <th key={i} scope="col" abbr={MONTH_NAMES[i]}>{m}</th>)}
            <th scope="col" className="matrix-count">Valid</th>
          </tr>
        </thead>
        <tbody>
          {annual.map((y) => (
            <tr key={y.year} className={y.eligible ? "" : "matrix-excluded"}>
              <th scope="row">{y.year}</th>
              {MONTHS.map((_, i) => {
                const m = i + 1;
                const state = y.represented_months === null ? "unknown" : y.represented_months.includes(m) ? "valid" : y.missing_months?.includes(m) ? "missing" : "unknown";
                const word = state === "valid" ? "valid" : state === "missing" ? "missing" : "not reported";
                return (
                  <td key={m} className={`mx mx-${state}`}>
                    <span className="sr-only">{MONTH_NAMES[i]} {y.year}: {word}</span>
                  </td>
                );
              })}
              <td className="matrix-count mono">{y.represented_months === null ? "—" : `${y.represented_months.length}/12`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
