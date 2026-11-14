import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import type { Analysis } from "../api/types";
import { fmt, reasonLabel } from "../lib/format";
import { isSeasonal } from "../lib/verdict";
import Disclosure from "./ui/Disclosure";
import { CHART, tickStyle } from "./science/chartTheme";

interface Row {
  year: number;
  eligible: number | null;
  excluded: number | null;
  trend: number | null;
  reasons: string[];
}

export function buildRows(a: Analysis): Row[] {
  const t = a.trend;
  const eligibleYears = t?.eligible_years ?? [];
  const lo = eligibleYears.length ? Math.min(...eligibleYears) : Infinity;
  const hi = eligibleYears.length ? Math.max(...eligibleYears) : -Infinity;
  return a.annual.map((y) => ({
    year: y.year,
    eligible: y.eligible ? y.value : null,
    excluded: !y.eligible ? y.value : null,
    trend: t && t.slope !== null && t.intercept !== null && y.year >= lo && y.year <= hi ? t.intercept + t.slope * y.year : null,
    reasons: y.reasons,
  }));
}

function TooltipBody({ active, payload, units }: { active?: boolean; payload?: Array<{ payload: Row }>; units: string }) {
  if (!active || !payload?.length) return null;
  const r = payload[0]!.payload;
  const value = r.eligible ?? r.excluded;
  return (
    <div className="chart-tooltip">
      <strong className="mono">{r.year}</strong>
      <div>{value === null ? "No annual value" : <><span className="mono">{fmt(value, 3)}</span> {units}</>}</div>
      {r.excluded !== null || (r.eligible === null && r.reasons.length) ? (
        <div className="tt-muted">Excluded: {r.reasons.map(reasonLabel).join("; ")}</div>
      ) : r.eligible !== null ? (
        <div className="tt-ok">Eligible for trend</div>
      ) : null}
      {r.trend !== null && <div className="tt-muted">Fitted trend: <span className="mono">{fmt(r.trend, 3)}</span></div>}
    </div>
  );
}

function yearTicks(rows: Row[]): number[] {
  const years = rows.map((r) => r.year);
  const step = Math.max(1, Math.ceil(years.length / 10));
  return years.filter((_, i) => i % step === 0 || i === years.length - 1);
}

type DotProps = { cx?: number; cy?: number; payload?: Row };
// Recharts still calls the shape for rows whose value is null; draw nothing for those.
const EligibleDot = (p: unknown) => {
  const { cx, cy, payload } = p as DotProps;
  if (cx === undefined || cy === undefined || payload?.eligible == null) return <g />;
  return <circle cx={cx} cy={cy} r={5.5} fill={CHART.obs} stroke={CHART.surface} strokeWidth={2} />;
};
const ExcludedDot = (p: unknown) => {
  const { cx, cy, payload } = p as DotProps;
  if (cx === undefined || cy === undefined || payload?.excluded == null) return <g />;
  return <circle cx={cx} cy={cy} r={5} fill={CHART.surface} stroke={CHART.excluded} strokeWidth={2} />;
};

export default function TrendChart({ analysis }: { analysis: Analysis }) {
  const rows = buildRows(analysis);
  const units = analysis.units.annual_value;
  const hasTrend = rows.some((r) => r.trend !== null);
  const hasExcluded = rows.some((r) => r.excluded !== null);
  const seasonal = isSeasonal(analysis);
  const trendName = seasonal ? "Seasonal Sen trend (from monthly values)" : "Theil–Sen trend (eligible years)";
  const cp = analysis.trend?.change_point;
  const stepAt = cp?.status === "step_detected" && cp.first_year_after !== undefined ? cp.first_year_after - 0.5 : null;
  return (
    <figure className="chart" aria-labelledby="trend-chart-title">
      <div className="chart-head">
        <div>
          <h3 id="trend-chart-title" className="chart-title">Annual values{hasTrend ? " and fitted trend" : ""}</h3>
          <p className="chart-sub">{analysis.variable.annual_value_definition} · <span className="mono">{units}</span></p>
        </div>
        <ul className="legend" aria-label="Legend">
          <li><span className="key key-dot" style={{ background: CHART.obs }} />Eligible annual value</li>
          {hasExcluded && <li><span className="key key-ring" style={{ borderColor: CHART.excluded }} />Excluded year (descriptive)</li>}
          {hasTrend && <li><span className="key key-line" style={{ background: CHART.trend }} />{trendName}</li>}
          {stepAt !== null && <li><span className="key key-line key-step" style={{ borderColor: CHART.step }} />Sudden step {cp?.last_year_before}–{cp?.first_year_after}</li>}
        </ul>
      </div>
      <div className="chart-plot" aria-hidden>
        <ResponsiveContainer width="100%" height={300}>
          <ComposedChart data={rows} margin={{ top: 12, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="year" type="number" domain={["dataMin", "dataMax"]} padding={{ left: 16, right: 16 }} allowDecimals={false} ticks={yearTicks(rows)} tick={tickStyle} stroke={CHART.axis} tickLine={false} />
            <YAxis domain={["auto", "auto"]} tick={tickStyle} stroke={CHART.axis} axisLine={false} tickLine={false} width={58} tickFormatter={(v: number) => fmt(v, 2)} />
            <Tooltip content={<TooltipBody units={units} />} cursor={{ stroke: CHART.axis, strokeDasharray: "2 3" }} />
            {stepAt !== null && <ReferenceLine x={stepAt} stroke={CHART.step} strokeDasharray="5 4" strokeWidth={1.5} ifOverflow="extendDomain" />}
            <Line name={trendName} dataKey="trend" stroke={CHART.trend} strokeWidth={2.5} dot={false} activeDot={false} connectNulls isAnimationActive={false} />
            <Scatter name="Eligible annual value" dataKey="eligible" shape={EligibleDot} isAnimationActive={false} />
            <Scatter name="Excluded year (descriptive)" dataKey="excluded" shape={ExcludedDot} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="chart-caption">
        {seasonal
          ? "The trend comes from monthly values compared month by month, so it does not depend on complete years. Annual means are shown for context only; hollow rings are years missing months."
          : "The trend line spans eligible years only. Hollow rings are years shown for context but excluded by the completeness rules."}
        {stepAt !== null && " The dashed line marks a sudden step: values jump once and stay at the new level, which often means a change in the data rather than gradual change."}
      </figcaption>
      <Disclosure summary="Annual data table" meta={`${rows.length} years`} className="chart-table">
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Annual {analysis.variable.name} values ({units}) and eligibility</caption>
            <thead><tr><th scope="col">Year</th><th scope="col">Annual value ({units})</th><th scope="col">Fitted trend</th><th scope="col">Status</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.year} className={r.eligible === null ? "row-excluded" : ""}>
                  <th scope="row" className="mono">{r.year}</th>
                  <td className="mono">{fmt(r.eligible ?? r.excluded, 3)}</td>
                  <td className="mono">{fmt(r.trend, 3)}</td>
                  <td>{r.eligible !== null ? "Eligible" : r.reasons.length ? r.reasons.map(reasonLabel).join("; ") : "No value"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Disclosure>
    </figure>
  );
}
