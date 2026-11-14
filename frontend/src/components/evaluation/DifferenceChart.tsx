import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PairComparison } from "../../api/compareTypes";
import { signed } from "../../lib/format";

export default function DifferenceChart({ pair, names }: { pair: PairComparison; names: [string, string] }) {
  if (!pair.annual_differences) {
    return <p className="note">A difference chart is unavailable because these products do not measure directly comparable quantities in compatible units.</p>;
  }
  const label = `${names[0]} minus ${names[1]}`;
  return (
    <section aria-labelledby="difference-heading">
      <h3 id="difference-heading" className="eval-subtitle">Dataset difference over time</h3>
      <p className="note"><strong>{label}.</strong> Differences are between products, not measurement errors against truth.</p>
      <figure className="chart-figure eval-difference-chart">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={pair.annual_differences} margin={{ top: 12, right: 18, bottom: 8, left: 12 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="year" />
            <YAxis unit={pair.difference_units ? ` ${pair.difference_units}` : undefined} />
            <Tooltip formatter={(value) => [`${signed(Number(value), 3)} ${pair.difference_units ?? ""}`, label]} />
            <Line type="monotone" dataKey="difference" name={label} stroke="var(--data-primary)" strokeWidth={2} dot />
          </LineChart>
        </ResponsiveContainer>
      </figure>
      <div className="table-wrap">
        <table className="table" aria-label="Matched product differences">
          <thead><tr><th>Period</th><th>{label}</th></tr></thead>
          <tbody>{pair.annual_differences.map((point) => <tr key={point.year}><td>{point.year}</td><td className="mono">{signed(point.difference, 3)} {pair.difference_units}</td></tr>)}</tbody>
        </table>
      </div>
    </section>
  );
}
