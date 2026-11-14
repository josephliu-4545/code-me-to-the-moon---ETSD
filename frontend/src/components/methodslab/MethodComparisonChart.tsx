import { CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import type { MethodsLab } from "../../api/methodsLabTypes";
import { fmt } from "../../lib/format";
import { CHART, tickStyle } from "../science/chartTheme";

export const OLS_COLOR = "var(--data-secondary)";

export interface ComparisonRow {
  year: number;
  eligible: number | null;
  excluded: number | null;
  ols: number | null;
  theil_sen: number | null;
}

/** Eligible and excluded observations plus both fitted lines, only within the eligible span. */
export function buildComparisonRows(lab: MethodsLab): ComparisonRow[] {
  const fitted = new Map((lab.comparison?.fitted ?? []).map((f) => [f.year, f]));
  const rows = new Map<number, ComparisonRow>();
  for (const e of lab.observations.eligible) {
    const f = fitted.get(e.year);
    rows.set(e.year, { year: e.year, eligible: e.value, excluded: null, ols: f?.ols ?? null, theil_sen: f?.theil_sen ?? null });
  }
  for (const x of lab.observations.excluded) {
    if (x.value === null) continue;
    rows.set(x.year, { year: x.year, eligible: null, excluded: x.value, ols: null, theil_sen: null });
  }
  return [...rows.values()].sort((a, b) => a.year - b.year);
}

type DotProps = { cx?: number; cy?: number; payload?: ComparisonRow };
const EligibleDot = (p: unknown) => {
  const { cx, cy, payload } = p as DotProps;
  if (cx === undefined || cy === undefined || payload?.eligible == null) return <g />;
  return <circle cx={cx} cy={cy} r={5} fill={CHART.obs} stroke={CHART.surface} strokeWidth={2} />;
};
const ExcludedDot = (p: unknown) => {
  const { cx, cy, payload } = p as DotProps;
  if (cx === undefined || cy === undefined || payload?.excluded == null) return <g />;
  return <circle cx={cx} cy={cy} r={5} fill="none" stroke={CHART.excluded} strokeWidth={2} />;
};

export default function MethodComparisonChart({ lab, units }: { lab: MethodsLab; units: string }) {
  const rows = buildComparisonRows(lab);
  return (
    <figure className="lab-figure" aria-label="Eligible annual observations with OLS and Theil–Sen lines fitted to the same years">
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={rows} margin={{ top: 10, right: 16, bottom: 4, left: 4 }}>
          <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" />
          <XAxis dataKey="year" type="number" domain={["dataMin", "dataMax"]} padding={{ left: 14, right: 14 }} allowDecimals={false} tick={tickStyle} stroke={CHART.axis} />
          <YAxis domain={["auto", "auto"]} tick={tickStyle} stroke={CHART.axis} width={64} tickFormatter={(v: number) => fmt(v, 2)} />
          <Tooltip formatter={(v, name) => [v == null ? "—" : `${fmt(Number(v), 3)} ${units}`, String(name)]} labelFormatter={(l) => `Year ${l}`}
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--border-strong)", color: "var(--text-primary)" }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Scatter name="Eligible observation" dataKey="eligible" shape={EligibleDot} isAnimationActive={false} legendType="circle" fill={CHART.obs} />
          <Scatter name="Excluded (not used)" dataKey="excluded" shape={ExcludedDot} isAnimationActive={false} legendType="circle" fill="none" />
          <Line name="Theil–Sen line" dataKey="theil_sen" stroke={CHART.trend} strokeWidth={2.5} dot={false} connectNulls isAnimationActive={false} />
          <Line name="OLS line (descriptive)" dataKey="ols" stroke={OLS_COLOR} strokeWidth={2} strokeDasharray="7 4" dot={false} connectNulls isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
      <figcaption className="note">
        Both lines are fitted to the same eligible years and drawn only across them; they summarise the past and are not forecasts. Hollow rings are excluded years, shown for context only.
      </figcaption>
      <details className="note lab-table-alt">
        <summary>Table of the plotted values</summary>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Year</th><th>Observed ({units})</th><th>Status</th><th>OLS line</th><th>Theil–Sen line</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.year}>
                  <td className="mono">{r.year}</td>
                  <td className="mono">{fmt(r.eligible ?? r.excluded, 3)}</td>
                  <td>{r.eligible !== null ? "eligible" : "excluded"}</td>
                  <td className="mono">{fmt(r.ols, 3)}</td>
                  <td className="mono">{fmt(r.theil_sen, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
