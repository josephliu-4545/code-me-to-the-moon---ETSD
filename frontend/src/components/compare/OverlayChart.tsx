import { CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DatasetResult } from "../../api/compareTypes";
import { fmt } from "../../lib/format";

// Mid-tone hues that read on both the dark (Orbit) and light (Mission Briefing) themes.
export const DATASET_COLORS = ["#3E97DD", "#C9822D", "#4FA37F", "#9C7FD6"];

export interface OverlayRow {
  year: number;
  [series: string]: number | null;
}

/** One row per year; eligible values, excluded values and the dataset's own trend line kept separate. */
export function buildOverlayRows(results: DatasetResult[]): OverlayRow[] {
  const years = new Set<number>();
  results.forEach((r) => r.analysis?.annual.forEach((a) => years.add(a.year)));
  return [...years].sort((a, b) => a - b).map((year) => {
    const row: OverlayRow = { year };
    for (const r of results) {
      const a = r.analysis!;
      const point = a.annual.find((x) => x.year === year);
      const key = r.entry.key;
      row[key] = point && point.eligible ? point.value : null;
      row[`${key}__excluded`] = point && !point.eligible ? point.value : null;
      const t = a.trend;
      const elig = t?.eligible_years ?? [];
      const inSpan = elig.length > 0 && year >= Math.min(...elig) && year <= Math.max(...elig);
      row[`${key}__trend`] = t && t.slope !== null && t.intercept !== null && inSpan ? t.intercept + t.slope * year : null;
    }
    return row;
  });
}

export default function OverlayChart({ results, units }: { results: DatasetResult[]; units: string }) {
  const rows = buildOverlayRows(results);
  return (
    <figure className="chart-figure" aria-label="Annual values of all datasets with their independent trend lines">
      <ResponsiveContainer width="100%" height={340}>
        <ComposedChart data={rows} margin={{ top: 10, right: 16, bottom: 4, left: 4 }}>
          <CartesianGrid stroke="rgba(169, 184, 206, 0.18)" strokeDasharray="3 3" />
          <XAxis dataKey="year" type="number" domain={["dataMin", "dataMax"]} padding={{ left: 14, right: 14 }} allowDecimals={false} tick={{ fill: "#8798B0", fontSize: 12 }} stroke="rgba(169, 184, 206, 0.32)" />
          <YAxis domain={["auto", "auto"]} tick={{ fill: "#8798B0", fontSize: 12 }} stroke="rgba(169, 184, 206, 0.32)" width={70} tickFormatter={(v: number) => fmt(v, 2)} />
          <Tooltip
            contentStyle={{ background: "#101D35", border: "1px solid rgba(169, 184, 206, 0.3)", color: "#F6F0E6" }}
            formatter={(v, name) => [v === null || v === undefined ? "—" : `${fmt(Number(v), 3)} ${units}`, String(name)]}
            labelFormatter={(l) => `Year ${l}`}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {results.map((r, i) => (
            <Line key={r.entry.key} name={r.entry.name} dataKey={r.entry.key} stroke={DATASET_COLORS[i % 4]} strokeWidth={2}
              dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />
          ))}
          {results.map((r, i) => (
            <Line key={`${r.entry.key}-t`} name={`${r.entry.name} — trend`} dataKey={`${r.entry.key}__trend`} stroke={DATASET_COLORS[i % 4]}
              strokeDasharray="6 4" strokeWidth={1.5} dot={false} connectNulls legendType="plainline" isAnimationActive={false} />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
      <figcaption className="note">
        Solid: eligible annual values ({units}); gaps are years excluded by that dataset's own rules. Dashed: each dataset's own Theil–Sen line over its eligible years. Datasets are drawn together only because they measure the same quantity in the same units; they are never merged.
      </figcaption>
    </figure>
  );
}
